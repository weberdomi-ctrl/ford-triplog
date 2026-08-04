# Ford Triplog OCR

Optional local OCR service for [Ford Triplog](https://github.com/weberdomi-ctrl/ford-triplog).

The service receives a PDF or image, runs RapidOCR locally and returns the
recognized text together with confidence values and bounding boxes.

Receipt parsing and assignment remain inside the Ford Triplog Home Assistant
integration. This container only performs OCR.

## Features

- Fully local processing
- RapidOCR with ONNX Runtime
- PDF, JPEG, PNG and WEBP support
- First-page PDF rendering
- Optional API-key protection
- Configurable upload limit and PDF resolution
- Health endpoint
- Interactive FastAPI documentation
- No cloud service required
- No permanent receipt storage

## Requirements

- Docker Engine with Docker Compose, or
- Synology Container Manager

The default container memory limit is 2 GB.

## Quick Start

1. Copy all repository files to the Docker host.
2. Create the environment file:

   ```bash
   cp .env.example .env
   ```

3. Edit `.env` and replace:

   ```text
   OCR_API_KEY=CHANGE_ME_LONG_RANDOM_KEY
   ```

   with a long random key.

4. Build and start the container:

   ```bash
   docker compose up -d --build
   ```

5. Check the service:

   ```bash
   curl http://localhost:9080/health
   ```

## Synology Container Manager

1. Create a folder, for example:

   ```text
   /volume1/docker/ford-triplog-ocr
   ```

2. Copy all repository files into the folder.
3. Copy `.env.example` to `.env`.
4. Replace the example API key in `.env`.
5. Open **Container Manager → Project → Create**.
6. Select the project folder.
7. Build and start the project.

## Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service and capability information |
| `POST` | `/ocr` | Run OCR for one uploaded document |
| `GET` | `/docs` | Interactive FastAPI documentation |

Default addresses:

```text
http://SERVER-IP:9080/health
http://SERVER-IP:9080/ocr
http://SERVER-IP:9080/docs
```

## Test OCR

```bash
curl -X POST   -H "X-API-Key: YOUR_API_KEY"   -F "file=@receipt.pdf"   http://SERVER-IP:9080/ocr
```

Supported media types:

- `application/pdf`
- `image/jpeg`
- `image/png`
- `image/webp`

PDF processing currently uses the first page only.

## Ford Triplog Configuration

In Home Assistant open:

```text
Settings
→ Devices & services
→ Ford Triplog
→ Configure
→ Settings
→ OCR Connection
```

Example values:

| Setting | Example |
|---|---|
| Enable OCR | Enabled |
| OCR service URL | `http://192.168.1.20:9080` |
| API key | Value from `.env` |
| Timeout | `30` seconds |

Ford Triplog tests the `/health` endpoint when the settings are saved.

## Environment Variables

| Variable | Default | Description |
|---|---:|---|
| `OCR_API_KEY` | empty/example | Optional API key checked through `X-API-Key` |
| `OCR_HOST_PORT` | `9080` | Port exposed on the Docker host |
| `OCR_MAX_FILE_MB` | `20` | Maximum upload size |
| `OCR_PDF_DPI` | `200` | PDF rendering resolution |
| `OCR_LOG_LEVEL` | `INFO` | Python log level |

When `OCR_API_KEY` is empty, the OCR endpoint does not require authentication.
For normal use, setting an API key is strongly recommended.

## Privacy and Security

- OCR processing is performed locally.
- The application does not upload documents to external services.
- Uploaded data is processed in memory.
- Do not expose port `9080` directly to the internet.
- Restrict access to the trusted local network.
- Use a long random API key.

## Logs

```bash
docker compose logs -f ford-triplog-ocr
```

## Updating

```bash
docker compose down
docker compose build --pull --no-cache
docker compose up -d
```

## API Documentation

See [docs/api.md](docs/api.md).

## Development Tests

Install development dependencies:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
pytest
```

## License

MIT License. See [LICENSE](LICENSE).
