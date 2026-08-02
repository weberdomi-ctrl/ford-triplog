Ford Triplog OCR 0.1.1 Hotfix

Behoben:
- NumPy-Arrays von RapidOCR werden ohne boolesche Auswertung verarbeitet.
- Kein HTTP-500 mehr bei `result.boxes`.
- Zusätzliche Logs für Anzahl erkannter Boxen, Texte und Bewertungen.
- Leere OCR-Ergebnisse werden als erfolgreiche Antwort mit Warnung behandelt.

Installation:
1. app.py im Synology-Projektordner ersetzen.
2. Projekt stoppen.
3. Projekt neu erstellen/neu bauen.
4. Im Browser /health prüfen; Version muss 0.1.1 sein.
