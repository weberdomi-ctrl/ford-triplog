"""Persistent receipt files for Ford Triplog."""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import RECEIPTS_DIR, RECEIPT_MAX_SIZE_BYTES, STORAGE_DIR
from .metadata_storage import FordTriplogMetadataStorage
from .ocr import FordTriplogReceiptOCR

_LOGGER = logging.getLogger(__name__)

ReceiptTargetType = Literal["pause", "charge"]
_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}


class FordTriplogReceiptStorage:
    """Import, list and remove receipt files."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._directory = Path(hass.config.path(".storage", STORAGE_DIR, RECEIPTS_DIR))
        self._metadata = FordTriplogMetadataStorage(hass)
        self._ocr = FordTriplogReceiptOCR(hass)

    async def async_setup(self) -> None:
        await self.hass.async_add_executor_job(
            self._directory.mkdir, 0o755, True, True
        )
        await self._metadata.async_setup()

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

    async def async_analyze(self, receipt_id: str) -> dict[str, Any]:
        """Run local OCR and persist status and result metadata."""

        normalized_id = str(receipt_id).strip()
        receipt = await self._metadata.get_receipt(normalized_id)
        if receipt is None:
            raise ValueError("Receipt was not found")

        filename = str(receipt.get("filename") or "").strip()
        if not filename:
            raise ValueError("Receipt filename is missing")
        path = self._directory / Path(filename).name

        await self._metadata.update_receipt(
            normalized_id,
            {
                "ocr_status": "running",
                "ocr_error": None,
            },
        )
        try:
            result = await self._ocr.async_analyze(path)
        except Exception as err:
            await self._metadata.update_receipt(
                normalized_id,
                {
                    "ocr_status": "failed",
                    "ocr_error": str(err)[:500],
                },
            )
            raise

        updated = await self._metadata.update_receipt(
            normalized_id,
            {
                "ocr_status": "completed",
                "ocr_error": None,
                "ocr_result": result,
                "ocr_confirmed": False,
            },
        )
        if updated is None:
            raise ValueError("Receipt disappeared while OCR was running")
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
        return response
