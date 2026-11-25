# Ford Triplog repository instructions

## Release workflow

- Keep `2.8.0` as the development branch for the 2.8.0 series.
- Create a dedicated branch for each release in this series, starting from the relevant commit on `2.8.0`. Follow the established 2.7.0 release workflow and naming conventions.
- Make the release-specific version and build updates on the dedicated release branch. Keep the version in `custom_components/ford_triplog/manifest.json` aligned with `VERSION` in `custom_components/ford_triplog/const.py`, and set `BUILD` there for the release.
- Write GitHub entries in English. Replies to issues opened in German may be in German. Release notes and push and merge messages are always in English.
