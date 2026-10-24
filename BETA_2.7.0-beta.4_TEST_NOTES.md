# Ford Triplog v2.7.0-beta.4 — Josef Testbeta

Basis: 2.7.0-beta.3 mit Ladepausen- und Kostenbestätigungs-Fix.

- STOPPED bei verbundenem Stecker bedeutet Pause, nicht Ladeende.
- Energiesegmente bei Unterbrechungen werden kumuliert.
- Automatisch berechnete Heimtarife werden nicht als manuell bestätigt markiert.
- Kostenbestätigung erfolgt durch OK im Kosteneditor.
- Bei reiner Bestätigung bleiben Kostenquelle und Werte erhalten.

## HACS-Veröffentlichung
1. Die Dateien aus diesem Archiv in den Repository-Branch übernehmen (nicht das ZIP selbst als HACS-Quelle hochladen).
2. Commit und Push ausführen.
3. Tag `v2.7.0-beta.4` auf genau diesem Commit erstellen.
4. GitHub Release für diesen Tag als **Pre-release** veröffentlichen.
5. Josef aktiviert in HACS die Beta-Versionen und installiert v2.7.0-beta.4.

Nicht als Stable-Release markieren.
