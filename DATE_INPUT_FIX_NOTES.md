# Beta 3 – Date input fix

- Cost entry dates accept `01.01.2026`, `01.01.26` and `2026-01-01`.
- Two-digit years map to 2000–2099.
- Normalization occurs on save; database values remain ISO.
- Invalid dates produce a field-specific error and preserve form entries.
- Existing database records are not migrated or rewritten.
- Home Assistant native date picker fields in export and tariff workflows remain native pickers; they use ISO dates internally.
