FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libxcb1 \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt \
    && python -c "import cv2; print('OpenCV:', cv2.__version__)"

COPY app.py .

RUN useradd --create-home --uid 1000 ocr \
    && mkdir -p /data \
    && chown -R ocr:ocr /app /data

USER ocr

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]