from __future__ import annotations

import io
import logging
import os
import statistics
import time
from typing import Any

import fitz
import numpy as np
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from PIL import Image
from rapidocr import RapidOCR

APP_NAME = "Ford Triplog OCR"
APP_VERSION = "0.1.1"

API_KEY = os.getenv("OCR_API_KEY", "").strip()
MAX_FILE_MB = int(os.getenv("OCR_MAX_FILE_MB", "20"))
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
PDF_DPI = int(os.getenv("OCR_PDF_DPI", "200"))
LOG_LEVEL = os.getenv("OCR_LOG_LEVEL", "INFO").upper()

SUPPORTED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
LOGGER = logging.getLogger("ford_triplog_ocr")

app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url=None,
)

LOGGER.info("Initialising RapidOCR engine")
ocr_engine = RapidOCR()
LOGGER.info("RapidOCR engine ready")


def _check_api_key(x_api_key: str | None) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def _pdf_first_page_to_image(data: bytes) -> np.ndarray:
    try:
        with fitz.open(stream=data, filetype="pdf") as document:
            if document.page_count < 1:
                raise ValueError("PDF contains no pages")
            page = document.load_page(0)
            zoom = PDF_DPI / 72.0
            pixmap = page.get_pixmap(
                matrix=fitz.Matrix(zoom, zoom),
                alpha=False,
            )
            image = Image.frombytes(
                "RGB",
                (pixmap.width, pixmap.height),
                pixmap.samples,
            )
            return np.asarray(image)
    except Exception as err:
        raise HTTPException(
            status_code=400,
            detail=f"PDF could not be rendered: {err}",
        ) from err


def _image_bytes_to_array(data: bytes) -> np.ndarray:
    try:
        with Image.open(io.BytesIO(data)) as image:
            return np.asarray(image.convert("RGB"))
    except Exception as err:
        raise HTTPException(
            status_code=400,
            detail=f"Image could not be decoded: {err}",
        ) from err


def _box_to_json(box: Any) -> list[list[float]] | None:
    if box is None:
        return None
    if hasattr(box, "tolist"):
        box = box.tolist()
    try:
        return [[float(x), float(y)] for x, y in box]
    except Exception:
        return None


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "engine": "rapidocr",
        "max_file_mb": MAX_FILE_MB,
        "pdf_first_page_only": True,
    }


@app.post("/ocr")
async def run_ocr(
    file: UploadFile = File(...),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_api_key(x_api_key)

    content_type = (file.content_type or "").lower()
    if content_type not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported content type: {content_type or 'unknown'}",
        )

    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_FILE_MB} MB",
        )
    if not data:
        raise HTTPException(status_code=400, detail="File is empty")

    if content_type == "application/pdf":
        image = _pdf_first_page_to_image(data)
        source_page = 1
    else:
        image = _image_bytes_to_array(data)
        source_page = None

    started = time.perf_counter()
    try:
        result = ocr_engine(image)
    except Exception as err:
        LOGGER.exception("OCR processing failed")
        raise HTTPException(
            status_code=500,
            detail=f"OCR processing failed: {err}",
        ) from err

    texts = (
        list(result.txts)
        if result.txts is not None
        else []
    )
    scores = (
        [float(value) for value in result.scores]
        if result.scores is not None
        else []
    )
    boxes = (
        result.boxes.tolist()
        if result.boxes is not None
        and hasattr(result.boxes, "tolist")
        else list(result.boxes)
        if result.boxes is not None
        else []
    )

    LOGGER.info(
        "OCR result prepared: file=%s boxes=%d texts=%d scores=%d",
        file.filename,
        len(boxes),
        len(texts),
        len(scores),
    )

    if not texts:
        LOGGER.warning(
            "OCR finished without recognized text: file=%s",
            file.filename,
        )

    lines: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        score = scores[index] if index < len(scores) else None
        box = boxes[index] if index < len(boxes) else None
        lines.append(
            {
                "text": str(text),
                "confidence": score,
                "box": _box_to_json(box),
            }
        )

    elapsed = round(time.perf_counter() - started, 3)
    raw_text = "\n".join(line["text"] for line in lines)
    confidence = (
        round(statistics.fmean(scores), 4)
        if scores
        else None
    )

    LOGGER.info(
        "OCR completed: file=%s type=%s lines=%s elapsed=%ss",
        file.filename,
        content_type,
        len(lines),
        elapsed,
    )

    return {
        "success": True,
        "engine": "rapidocr",
        "service_version": APP_VERSION,
        "filename": file.filename,
        "media_type": content_type,
        "source_page": source_page,
        "elapsed_seconds": elapsed,
        "confidence": confidence,
        "raw_text": raw_text,
        "lines": lines,
    }
