# Ford Triplog charging database generator

## Dateien

- `build_charging_database.py` – Hauptprogramm
- `countries.py` – unterstützte Länder
- `overpass.py` – Overpass-Abfrage und Download
- `normalizer.py` – OSM-Tags normalisieren
- `geohash.py` – räumlicher Index

## Schweiz online erzeugen

```bash
cd tools
python build_charging_database.py CH
```

Die Datei wird erstellt unter:

```text
custom_components/ford_triplog/charging_database/ch.json.gz
```

## Ohne Download testen

```bash
python build_charging_database.py CH --input sample_overpass_ch.json
```

## Rohdaten sichern

```bash
python build_charging_database.py CH --save-raw raw/ch.json
```

Der Generator benötigt nur Python 3.11 oder neuer und keine Zusatzpakete.
