# Ford Triplog Charging Database – Phase 1

Frozen status: **completed**  
Project version: **1.4.0**  
Freeze date: **2026-07-23**

## Included pipeline

1. `overpass.py` downloads raw OpenStreetMap charging-station data.
2. `normalizer.py` normalizes provider, connector and station data.
3. `validator.py` validates the normalized database.
4. `geohash_index.py` builds the geohash-indexed offline database.

## Tested Switzerland result

- Raw/normalized stations: 3,626
- Stations indexed: 3,626
- Skipped stations: 0
- Geohash precision: 6
- Geohash buckets: 2,414
- Largest bucket: 12
- Average bucket size: 1.5
- Brand available: 2,798 (77.2%)
- Missing coordinates: 0
- Duplicate OSM IDs: 0

Nearby OSM records are intentionally retained. Logical site clustering and charging-site lookup belong to Phase 2.

## Required Python package

```powershell
pip install requests
```

## Run order

From the `tools` directory:

```powershell
python overpass.py
python normalizer.py
python validator.py
python geohash_index.py
```

Generated files:

- `overpass_ch_raw.json`
- `charging_stations_ch_normalized.json`
- `charging_database_ch.json`

## Frozen source versions

- Normalizer: `1.4.0-dev.005`
- Validator: `1.4.0-dev.002`
- Geohash indexer: `1.4.0-dev.001`
- Overpass/countries package state: `1.4.0-phase1`

The `frozen_sources` directory contains immutable reference copies of the tested development files.
