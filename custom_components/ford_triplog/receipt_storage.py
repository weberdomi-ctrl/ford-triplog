"""Persistent receipt files for Ford Triplog."""

from __future__ import annotations

import json

import logging
import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import (
    RECEIPTS_DIR,
    RECEIPT_MAX_SIZE_BYTES,
    STORAGE_DIR,
    STORAGE_READ_BACKEND_SQLITE,
)
from .metadata_storage import FordTriplogMetadataStorage
from .receipt_parser import ReceiptParserEngine


if TYPE_CHECKING:
    from .ocr_client import FordTriplogOCRClient

_LOGGER = logging.getLogger(__name__)

ReceiptTargetType = Literal["pause", "charge"]
_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


class FordTriplogReceiptStorage:
    """Import, list and remove receipt files."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._directory = Path(
            hass.config.path(".storage", STORAGE_DIR, RECEIPTS_DIR)
        )
        self._user_profile_directory = Path(
            hass.config.path(
                ".storage",
                STORAGE_DIR,
                "receipt_parser_profiles",
            )
        )
        self._metadata = FordTriplogMetadataStorage(hass)
        self._parser = ReceiptParserEngine(
            Path(__file__).parent / "receipt_parser_profiles",
            (
                None
                if self._metadata.read_backend == STORAGE_READ_BACKEND_SQLITE
                else self._user_profile_directory
            ),
        )

    async def async_setup(self) -> None:
        await self.hass.async_add_executor_job(
            self._directory.mkdir, 0o755, True, True
        )
        await self._metadata.async_setup()

        if self._metadata.read_backend == STORAGE_READ_BACKEND_SQLITE:
            profiles = (
                await self._metadata.database.load_user_receipt_parser_profiles()
            )

            # One-time recovery from legacy user JSON profiles when SQLite
            # is still empty. Bundled profiles are never imported.
            if not profiles and await self.hass.async_add_executor_job(
                self._user_profile_directory.is_dir
            ):
                legacy_profiles = await self.hass.async_add_executor_job(
                    self._load_user_profiles_from_json
                )
                if legacy_profiles:
                    saved = await self._metadata.database.save_all_user_receipt_parser_profiles(
                        legacy_profiles
                    )
                    if not saved:
                        raise OSError(
                            "Unable to migrate user receipt parser profiles to SQLite"
                        )
                    profiles = legacy_profiles
                    _LOGGER.info(
                        "Imported %d user receipt parser profiles from JSON into SQLite",
                        len(profiles),
                    )

            self._parser.set_user_profiles(profiles)
            await self.hass.async_add_executor_job(self._parser.load)
            return

        await self.hass.async_add_executor_job(
            self._user_profile_directory.mkdir,
            0o755,
            True,
            True,
        )
        await self.hass.async_add_executor_job(self._parser.load)

    async def async_import(
        self,
        source_path: str | Path,
        *,
        target_type: ReceiptTargetType,
        target_id: str,
        original_name: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        """Validate and copy an uploaded receipt into persistent storage."""

        if target_type not in ("pause", "charge"):
            raise ValueError("Unsupported receipt target type")
        normalized_target_id = str(target_id).strip()
        if not normalized_target_id:
            raise ValueError("Receipt target ID is required")

        source = Path(source_path)
        supplied_name = Path(original_name or source.name).name
        suffix = Path(supplied_name).suffix.lower() or source.suffix.lower()
        if suffix not in _ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported receipt file type")

        size_bytes = await self.hass.async_add_executor_job(self._validate_source, source)
        receipt_id = f"receipt_{uuid4().hex}"
        timestamp = datetime.now(timezone.utc)
        safe_target = self._safe_name(normalized_target_id)[:48]
        destination_name = (
            f"{timestamp:%Y%m%dT%H%M%SZ}_{target_type}_{safe_target}_{receipt_id[-12:]}{suffix}"
        )
        destination = self._directory / destination_name

        await self.hass.async_add_executor_job(self._copy_atomic, source, destination)

        media_type = mimetypes.guess_type(supplied_name)[0] or "application/octet-stream"
        receipt = {
            "receipt_id": receipt_id,
            "filename": destination_name,
            "original_filename": supplied_name,
            "media_type": media_type,
            "size_bytes": size_bytes,
            "created_at": timestamp.isoformat(),
            "note": str(note or "").strip(),
            "ocr_status": "not_started",
        }
        try:
            await self._metadata.add_receipt(target_type, normalized_target_id, receipt)
        except Exception:
            await self.hass.async_add_executor_job(destination.unlink, True)
            raise
        return receipt

    async def async_list(self) -> list[dict[str, Any]]:
        return await self._metadata.get_all_receipts()

    async def async_analyze(
        self,
        receipt_id: str,
        client: "FordTriplogOCRClient",
    ) -> dict[str, Any]:
        """Run external OCR and persist status and complete raw result."""

        normalized_id = str(receipt_id).strip()
        receipt = await self._metadata.get_receipt(normalized_id)
        if receipt is None:
            raise ValueError("Receipt was not found")

        filename = str(receipt.get("filename") or "").strip()
        if not filename:
            raise ValueError("Receipt filename is missing")

        path = self._directory / Path(filename).name
        if not await self.hass.async_add_executor_job(path.is_file):
            raise ValueError("Receipt file was not found")

        await self._metadata.update_receipt(
            normalized_id,
            {
                "ocr_status": "running",
                "ocr_error": None,
            },
        )

        try:
            content = await self.hass.async_add_executor_job(path.read_bytes)
            result = await client.async_analyze(
                filename=str(
                    receipt.get("original_filename")
                    or path.name
                ),
                media_type=str(
                    receipt.get("media_type")
                    or mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream"
                ),
                content=content,
            )
        except Exception as err:
            await self._metadata.update_receipt(
                normalized_id,
                {
                    "ocr_status": "failed",
                    "ocr_error": str(err)[:500],
                },
            )
            raise

        completed_at = datetime.now(timezone.utc).isoformat()
        result["completed_at"] = completed_at

        try:
            parse_result = self._parser.parse(
                str(result.get("raw_text") or "")
            )
            parse_data = parse_result.as_dict()
        except Exception:
            _LOGGER.exception(
                "Receipt parser failed after successful OCR: receipt_id=%s "
                "filename=%s",
                normalized_id,
                filename,
            )
            raise

        _LOGGER.info(
            "Receipt OCR and parser completed: receipt_id=%s "
            "ocr_engine=%s parse_status=%s parser_profile=%s",
            normalized_id,
            result.get("engine"),
            parse_result.status,
            parse_result.profile_id,
        )

        updated = await self._metadata.update_receipt(
            normalized_id,
            {
                "ocr_status": "completed",
                "ocr_error": None,
                "ocr_result": result,
                "ocr_confirmed": False,
                "parse_status": parse_result.status,
                "parser_profile": parse_result.profile_id,
                "parser_result": parse_data,
                "parser_confirmed": False,
            },
        )
        if updated is None:
            raise ValueError("Receipt disappeared while OCR was running")
        return updated


    async def async_create_user_parser_profile(
        self,
        profile: dict[str, Any],
    ) -> Path:
        """Persist one user-created parser profile and reload profiles."""

        profile_id = self._safe_name(
            str(profile.get("profile_id") or "")
        )
        if not profile_id:
            raise ValueError("Parser profile ID is required")

        normalized_profile = dict(profile)
        normalized_profile["profile_id"] = profile_id
        destination = self._user_profile_directory / f"{profile_id}.json"

        if self._metadata.read_backend == STORAGE_READ_BACKEND_SQLITE:
            saved = await self._metadata.database.save_user_receipt_parser_profile(
                normalized_profile
            )
            if not saved:
                raise OSError(
                    "Unable to save user receipt parser profile to SQLite"
                )

            profiles = (
                await self._metadata.database.load_user_receipt_parser_profiles()
            )
            self._parser.set_user_profiles(profiles)
            await self.hass.async_add_executor_job(self._parser.load)

            # Preserve the existing method contract. In SQLite mode this path
            # is only a logical legacy location; no JSON file is written.
            return destination

        payload = json.dumps(
            normalized_profile,
            ensure_ascii=False,
            indent=2,
        ) + "\n"

        await self.hass.async_add_executor_job(
            self._write_text_atomic,
            destination,
            payload,
        )
        await self.hass.async_add_executor_job(self._parser.load)
        return destination

    async def async_reparse(
        self,
        receipt_id: str,
    ) -> dict[str, Any]:
        """Reparse saved OCR text without running OCR again."""

        normalized_id = str(receipt_id).strip()
        receipt = await self._metadata.get_receipt(normalized_id)
        if receipt is None:
            raise ValueError("Receipt was not found")

        ocr_result = receipt.get("ocr_result", {})
        if not isinstance(ocr_result, dict):
            raise ValueError("Receipt has no OCR result")

        raw_text = str(ocr_result.get("raw_text") or "")
        if not raw_text.strip():
            raise ValueError("Receipt has no OCR text")

        parse_result = self._parser.parse(raw_text)
        parse_data = parse_result.as_dict()

        updated = await self._metadata.update_receipt(
            normalized_id,
            {
                "parse_status": parse_result.status,
                "parser_profile": parse_result.profile_id,
                "parser_result": parse_data,
                "parser_confirmed": False,
            },
        )
        if updated is None:
            raise ValueError("Receipt was not found")
        return updated



    async def async_mark_applied(
        self,
        receipt_id: str,
        *,
        charge_id: str,
        applied_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Mark parsed receipt values as reviewed and applied."""

        updated = await self._metadata.update_receipt(
            str(receipt_id).strip(),
            {
                "parser_confirmed": True,
                "applied_to_charge_id": str(charge_id).strip(),
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "applied_values": dict(applied_values),
            },
        )
        if updated is None:
            raise ValueError("Receipt was not found")
        return updated


    async def async_get(self, receipt_id: str) -> dict[str, Any] | None:
        """Return one receipt by its stable ID."""

        normalized = str(receipt_id).strip()
        for receipt in await self.async_list():
            if str(receipt.get("receipt_id") or "") == normalized:
                return receipt
        return None

    def get_managed_path(self, receipt: dict[str, Any]) -> Path | None:
        """Return the validated managed path for one receipt."""

        filename = Path(str(receipt.get("filename") or "")).name
        if not filename:
            return None
        path = self._directory / filename
        try:
            path.resolve().relative_to(self._directory.resolve())
        except ValueError:
            return None
        return path

    async def async_remove(self, receipt_id: str) -> dict[str, Any] | None:
        """Remove metadata and the corresponding managed file."""

        receipt = await self._metadata.remove_receipt(str(receipt_id).strip())
        if receipt is None:
            return None
        filename = str(receipt.get("filename") or "").strip()
        if filename:
            path = self._directory / Path(filename).name
            try:
                await self.hass.async_add_executor_job(path.unlink, True)
            except OSError:
                _LOGGER.exception("Unable to delete receipt file %s", path)
        return receipt

    def _load_user_profiles_from_json(self) -> list[dict[str, Any]]:
        """Load legacy user profiles only from the persistent data folder."""

        if not self._user_profile_directory.is_dir():
            return []

        profiles: list[dict[str, Any]] = []
        used_ids: set[str] = set()

        for path in sorted(self._user_profile_directory.glob("*.json")):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    profile = json.load(handle)
            except (OSError, json.JSONDecodeError):
                _LOGGER.exception(
                    "Unable to read legacy user receipt parser profile: %s",
                    path,
                )
                continue

            if not isinstance(profile, dict):
                continue

            profile_id = str(profile.get("profile_id") or "").strip()
            if (
                not profile_id
                or profile_id in used_ids
                or not isinstance(profile.get("match"), dict)
            ):
                continue

            used_ids.add(profile_id)
            profiles.append(profile)

        return profiles

    def _validate_source(self, source: Path) -> int:
        if not source.is_file():
            raise ValueError("Uploaded receipt does not exist")
        size = source.stat().st_size
        if size <= 0:
            raise ValueError("Uploaded receipt is empty")
        if size > RECEIPT_MAX_SIZE_BYTES:
            raise ValueError("Uploaded receipt is too large")
        return size

    @staticmethod
    def _safe_name(value: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
        return cleaned.strip("_") or "item"

    @staticmethod
    def _write_text_atomic(destination: Path, content: str) -> None:
        """Write UTF-8 text atomically."""

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            temporary.write_text(content, encoding="utf-8")
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    @staticmethod
    def _copy_atomic(source: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


class FordTriplogReceiptView(HomeAssistantView):
    """Authenticated HTTP view for opening a managed receipt."""

    url = "/api/ford_triplog/receipts/{receipt_id}"
    name = "api:ford_triplog:receipt"
    requires_auth = True

    async def get(self, request: web.Request, receipt_id: str) -> web.StreamResponse:
        """Return a PDF or image inline in the browser."""

        hass: HomeAssistant = request.app["hass"]
        domain_data = hass.data.get("ford_triplog", {})
        receipt: dict[str, Any] | None = None
        storage: FordTriplogReceiptStorage | None = None

        for runtime in domain_data.values():
            if not isinstance(runtime, dict):
                continue
            candidate = runtime.get("receipt_storage")
            if not isinstance(candidate, FordTriplogReceiptStorage):
                continue
            found = await candidate.async_get(receipt_id)
            if found is not None:
                receipt = found
                storage = candidate
                break

        if receipt is None or storage is None:
            raise web.HTTPNotFound()

        path = storage.get_managed_path(receipt)
        if path is None or not await hass.async_add_executor_job(path.is_file):
            raise web.HTTPNotFound()

        original_name = Path(
            str(receipt.get("original_filename") or path.name)
        ).name.replace('"', "")
        response = web.FileResponse(path)
        response.headers["Content-Disposition"] = (
            f'inline; filename="{original_name}"'
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "private, no-store"
        return response
