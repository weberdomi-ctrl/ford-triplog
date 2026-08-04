# Ford Triplog OCR API

Base URL example:

```text
http://192.168.1.20:9080
```

## Authentication

When `OCR_API_KEY` is configured, requests to `POST /ocr` must include:

```http
X-API-Key: dcbf8d53-0db0-4d6c-a6c6-8f38cf4f6c8d-3e61f7c40dcb
```

The `GET /health` endpoint does not require authentication.

## GET /health

Returns service and capability information.

Example request:

```bash
curl http://192.168.1.20:9080/health
```

Example response:

```json
{
  "status": "ok",
  "service": "Ford Triplog OCR",
  "version": "0.1.1",
  "engine": "rapidocr",
  "max_file_mb": 20,
  "pdf_first_page_only": true
}
```

## POST /ocr

Runs OCR for one uploaded document.

The request must use `multipart/form-data` with the form field `file`.

Example:

```bash
curl -X POST   -H "X-API-Key: your-secret-key"   -F "file=@receipt.pdf"   http://192.168.1.20:9080/ocr
```

Supported content types:

- `application/pdf`
- `image/jpeg`
- `image/png`
- `image/webp`

Example response:

```json
{
  "success": true,
  "engine": "rapidocr",
  "service_version": "0.1.1",
  "filename": "receipt.pdf",
  "media_type": "application/pdf",
  "source_page": 1,
  "elapsed_seconds": 1.234,
  "confidence": 0.9432,
  "raw_text": "Recognized receipt text",
  "lines": [
    {
      "text": "Recognized receipt text",
      "confidence": 0.9432,
      "box": [
        [10.0, 20.0],
        [200.0, 20.0],
        [200.0, 45.0],
        [10.0, 45.0]
      ]
    }
  ]
}
```

For image uploads, `source_page` is `null`.

## Error Responses

### 400 Bad Request

Examples:

- Empty file
- Invalid image data
- PDF could not be rendered
- PDF contains no pages

### 401 Unauthorized

The supplied API key does not match `OCR_API_KEY`.

```json
{
  "detail": "Invalid API key"
}
```

### 413 Content Too Large

The uploaded file exceeds `OCR_MAX_FILE_MB`.

### 415 Unsupported Media Type

The uploaded file type is not supported.

### 500 Internal Server Error

RapidOCR failed while processing the document.

## OpenAPI Documentation

Interactive API documentation is available at:

```text
http://SERVER-IP:9080/docs
```
