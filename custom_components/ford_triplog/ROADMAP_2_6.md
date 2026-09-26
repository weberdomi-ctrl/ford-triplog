# Ford Triplog 2.6 – Recovery roadmap

- Persist each vehicle's Home Assistant entity/sensor mapping in `ford_triplog.db` as recovery metadata.
- Keep the Home Assistant ConfigEntry as the active runtime configuration; the database copy is a restore template, not the live source of truth.
- On restore, match vehicles primarily by VIN/internal vehicle identity, validate whether saved entity IDs still exist, and offer remapping when they do not.
- Goal: restoring `ford_triplog.db` should recover nearly all Ford Triplog domain data and provide enough metadata to reconstruct vehicle configuration with minimal manual work.
