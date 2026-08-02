# Ford Triplog OCR Container

Lokaler OCR-Dienst für Ford Triplog.

## Synology Container Manager

1. Einen Ordner anlegen, z. B.:
   `/volume1/docker/ford-triplog-ocr`
2. Alle Dateien aus diesem Paket in den Ordner kopieren.
3. In `docker-compose.yml` den Wert `CHANGE_ME_LONG_RANDOM_KEY` ersetzen.
4. Container Manager → Projekt → Erstellen.
5. Als Quelle den Ordner auswählen und das Projekt bauen/starten.

## Endpunkte

- Health: `GET http://NAS-IP:9080/health`
- OCR: `POST http://NAS-IP:9080/ocr`
- API-Dokumentation: `http://NAS-IP:9080/docs`

## Test

```bash
curl http://NAS-IP:9080/health
```

```bash
curl -X POST   -H "X-API-Key: DEIN_API_KEY"   -F "file=@beleg.pdf"   http://NAS-IP:9080/ocr
```

## Hinweise

- PDF: aktuell wird nur die erste Seite verarbeitet.
- Maximalgrösse: standardmässig 20 MB.
- Der Port 9080 muss nur im lokalen Netz erreichbar sein.
- Keine Portweiterleitung ins Internet einrichten.
