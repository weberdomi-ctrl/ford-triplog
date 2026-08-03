"""Optional HTTP client for the external Ford Triplog OCR service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import async_timeout
from aiohttp import (
    ClientError,
    ClientResponseError,
    ClientSession,
    FormData,
)


class FordTriplogOCRError(Exception):
    """Base exception for OCR client errors."""


class FordTriplogOCRConnectionError(FordTriplogOCRError):
    """Raised when the OCR service cannot be reached."""


class FordTriplogOCRAuthenticationError(FordTriplogOCRError):
    """Raised when the OCR service rejects the API key."""


class FordTriplogOCRResponseError(FordTriplogOCRError):
    """Raised when the OCR service returns an invalid response."""


@dataclass(slots=True)
class FordTriplogOCRHealth:
    """Health information returned by the OCR service."""

    status: str
    service: str
    version: str
    engine: str
    max_file_mb: int | None
    pdf_first_page_only: bool | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FordTriplogOCRHealth":
        """Create health information from a JSON response."""

        status = str(data.get("status") or "").strip().lower()
        if status != "ok":
            raise FordTriplogOCRResponseError(
                f"OCR service returned status {status or 'unknown'}"
            )

        return cls(
            status=status,
            service=str(data.get("service") or "Ford Triplog OCR"),
            version=str(data.get("version") or "—"),
            engine=str(data.get("engine") or "—"),
            max_file_mb=(
                int(data["max_file_mb"])
                if data.get("max_file_mb") is not None
                else None
            ),
            pdf_first_page_only=(
                bool(data["pdf_first_page_only"])
                if data.get("pdf_first_page_only") is not None
                else None
            ),
        )


class FordTriplogOCRClient:
    """Client for the optional external Ford Triplog OCR service."""

    def __init__(
        self,
        session: ClientSession,
        base_url: str,
        api_key: str = "",
        timeout_seconds: int = 15,
    ) -> None:
        self._session = session
        self._base_url = str(base_url or "").strip().rstrip("/") + "/"
        self._api_key = str(api_key or "").strip()
        self._timeout_seconds = max(3, min(int(timeout_seconds), 120))

        if not self._base_url.startswith(("http://", "https://")):
            raise ValueError("OCR service URL must start with http:// or https://")

    @property
    def base_url(self) -> str:
        """Return the normalized base URL."""

        return self._base_url.rstrip("/")

    async def async_health(self) -> FordTriplogOCRHealth:
        """Fetch and validate OCR service health information."""

        url = urljoin(self._base_url, "health")
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        try:
            async with async_timeout.timeout(self._timeout_seconds):
                response = await self._session.get(url, headers=headers)
                if response.status in (401, 403):
                    raise FordTriplogOCRAuthenticationError(
                        "OCR service rejected the API key"
                    )
                response.raise_for_status()
                data = await response.json(content_type=None)
        except FordTriplogOCRError:
            raise
        except (ClientResponseError, ClientError, TimeoutError) as err:
            raise FordTriplogOCRConnectionError(str(err)) from err
        except ValueError as err:
            raise FordTriplogOCRResponseError(
                "OCR service returned invalid JSON"
            ) from err

        if not isinstance(data, dict):
            raise FordTriplogOCRResponseError(
                "OCR service returned an unexpected response"
            )

        return FordTriplogOCRHealth.from_dict(data)

    async def async_analyze(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> dict[str, Any]:
        """Send one receipt to the external OCR service."""

        if not content:
            raise ValueError("Receipt content is empty")

        url = urljoin(self._base_url, "ocr")
        headers: dict[str, str] = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        form = FormData()
        form.add_field(
            "file",
            content,
            filename=str(filename or "receipt"),
            content_type=str(media_type or "application/octet-stream"),
        )

        try:
            async with async_timeout.timeout(self._timeout_seconds):
                response = await self._session.post(
                    url,
                    headers=headers,
                    data=form,
                )
                if response.status in (401, 403):
                    raise FordTriplogOCRAuthenticationError(
                        "OCR service rejected the API key"
                    )
                if response.status == 413:
                    raise FordTriplogOCRResponseError(
                        "Receipt exceeds OCR service file-size limit"
                    )
                if response.status == 415:
                    raise FordTriplogOCRResponseError(
                        "OCR service rejected the receipt file type"
                    )
                response.raise_for_status()
                data = await response.json(content_type=None)
        except FordTriplogOCRError:
            raise
        except (ClientResponseError, ClientError, TimeoutError) as err:
            raise FordTriplogOCRConnectionError(str(err)) from err
        except ValueError as err:
            raise FordTriplogOCRResponseError(
                "OCR service returned invalid JSON"
            ) from err

        if not isinstance(data, dict):
            raise FordTriplogOCRResponseError(
                "OCR service returned an unexpected response"
            )
        if data.get("success") is not True:
            raise FordTriplogOCRResponseError(
                str(data.get("detail") or "OCR processing failed")
            )

        raw_text = str(data.get("raw_text") or "")
        lines = data.get("lines")
        if not isinstance(lines, list):
            lines = []

        return {
            "engine": str(data.get("engine") or "rapidocr"),
            "service_version": str(data.get("service_version") or "—"),
            "elapsed_seconds": (
                float(data["elapsed_seconds"])
                if data.get("elapsed_seconds") is not None
                else None
            ),
            "confidence": (
                float(data["confidence"])
                if data.get("confidence") is not None
                else None
            ),
            "source_page": data.get("source_page"),
            "media_type": str(data.get("media_type") or media_type),
            "raw_text": raw_text,
            "lines": lines,
        }
