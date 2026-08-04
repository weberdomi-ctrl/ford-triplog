# OCR Receipt Recognition

Ford Triplog supports an optional local OCR service for automatic receipt recognition.

OCR is **completely optional**.

Ford Triplog works without OCR. Receipts can always be uploaded and managed manually.

---

# Features

The OCR service can automatically extract information from charging receipts.

Supported information includes:

- Charging provider
- Charging station
- Charging start time
- Charging end time
- Energy delivered
- Price per kWh
- Total cost
- Charging duration
- Voltage
- Current
- Charging power
- Temperature (if available)

The extracted values can be reviewed before they are applied to a charging session.

---

# Privacy

OCR runs completely locally.

No receipt images or extracted data are sent to external cloud services.

All processing happens inside your own network.

---

# Requirements

The OCR service runs separately from Home Assistant.

Recommended installation:

- Docker
- Docker Compose
- Synology Container Manager
- Unraid
- Proxmox
- Linux

---

# Installing the OCR Service

Example Docker Compose:

```yaml
services:
  ford-triplog-ocr:
    image: ghcr.io/weberdomi-ctrl/ford-triplog-ocr:latest
    container_name: ford-triplog-ocr

    restart: unless-stopped

    ports:
      - "9080:8000"

    environment:
      OCR_API_KEY: your-secret-api-key
      OCR_MAX_FILE_MB: 20
      OCR_PDF_DPI: 200
      OCR_LOG_LEVEL: INFO

    volumes:
      - ./data:/data
```

Start the container:

```bash
docker compose up -d
```

### Verify the installation

Open the following URL in your browser:

```
http://YOUR_SERVER_IP:9080/health
```

Expected response:

```json
{
  "status": "ok",
  "service": "Ford Triplog OCR",
  "version": "1.0.0"
}
```

# Configuring Home Assistant

Open:

Settings

→ Devices & Services

→ Ford Triplog

→ Configure

→ Settings

→ OCR Connection

Configure:

| Setting | Example |
|---------|----------|
| Enable OCR | Enabled |
| OCR URL | http://192.168.1.10:9080 |
| API Key | your-secret-key |
| Timeout | 30 seconds |

Ford Triplog automatically performs a connection test.

If successful, the following information is displayed:

- Service version
- OCR engine
- Maximum file size
- PDF support

---

# Uploading Receipts

Open a charging session.

Select:

Receipts

→ Add Receipt

Supported formats:

- PDF
- JPG
- PNG
- WEBP

If OCR is enabled:

1. Receipt is uploaded.
2. OCR starts automatically.
3. Parser profile is detected.
4. Extracted values are displayed.
5. Values can be applied to the charging session.

---

# OCR Status

Each receipt displays its current status.

Possible states:

| Status | Description |
|---------|-------------|
| Not Started | OCR has not been executed |
| Queued | Waiting for processing |
| Running | OCR is currently processing |
| Completed | OCR completed successfully |
| Failed | OCR failed |
| Values Detected | Parser extracted charging values |
| Values Applied | Parsed values have been applied |

---

# Parser Profiles

Parser profiles allow automatic recognition of receipts from specific charging providers.

A profile contains:

- Provider identifier
- Matching text
- Extraction rules

When a receipt matches a profile, charging data is extracted automatically.

Custom parser profiles can be created directly from Home Assistant.

---

# Supported Receipt Types

Typical charging receipts from:

- Ionity
- Fastned
- Tesla Supercharger
- EnBW
- Aral Pulse
- Shell Recharge
- MOVE
- evpass

Additional providers can be supported through custom parser profiles.

---

# Troubleshooting

## Connection failed

Verify:

- Container is running
- Correct URL
- Correct API key
- Port 9080 reachable

Test:

```
http://your-server:9080/health
```

---

## OCR does not recognize a receipt

Possible reasons:

- Low image quality
- Unsupported receipt layout
- Missing parser profile

The OCR text can still be viewed and used to create a new parser profile.

---

## PDF upload fails

Verify:

- PDF is not password protected
- File size is within the configured limit

---

# FAQ

## Is OCR required?

No.

Ford Triplog works completely without OCR.

---

## Is internet access required?

No.

OCR runs entirely locally.

---

## Are my receipts uploaded to the cloud?

No.

All files remain on your own system.

---

## Can I add my own receipt formats?

Yes.

Custom parser profiles can be created directly from Home Assistant.

---

# Future Improvements

Planned enhancements include:

- Additional parser profiles
- Better multi-page PDF support
- Improved OCR accuracy
- Community-contributed parser profiles