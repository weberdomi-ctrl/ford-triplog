Ford Triplog 1.1.0



Release: 16.07.2026



Neu

Neuer Home Assistant Config Flow

Neuer Options Flow

Smart Trip Funktion hinzugefügt

Smart Trip Timeout einstellbar

Unterstützung für Home Assistant 2026.6

Neues Integration Branding (Home Assistant Brands Proxy API)

Neue Übersetzungen (Deutsch/Englisch)

Verbesserte Konfigurationsverwaltung

Verbesserungen

Modernisierte Integration gemäß aktuellen Home Assistant Richtlinien

Optimierter Config Entry Aufbau

Optionen können ohne Neuinstallation geändert werden

Verbesserte Initialisierung der Integration

Verbesserte Reload-Unterstützung nach Optionsänderungen

Aktualisierte Ordnerstruktur für Branding (brand/)

Zahlreiche interne Codebereinigungen

Vorbereitungen für zukünftige Funktionen

Fehlerbehebungen

Mehrere Probleme im Config Flow behoben

Options Flow vollständig überarbeitet

Fehler beim Speichern von Optionen behoben

Fehler beim Reload der Integration behoben

Kompatibilität mit Home Assistant Core 2026.6 hergestellt

Branding wird nun korrekt über die neue Brands Proxy API geladen

Bekannte Einschränkungen

Smart Trip befindet sich weiterhin in der ersten Ausbaustufe.

Ladeereignisse werden noch nicht separat ausgewertet.

Fahrtenexport ist noch nicht verfügbar.

Nächste Version (1.2.0)



Geplant sind unter anderem:



Ladehistorie

Erkennung von AC/DC-Ladevorgängen

Energieauswertung

Erweiterte Fahrstatistiken

Exportfunktionen

Weitere Sensoren



\--------------------------------------------------------------



Ford Triplog v1.0.0 Final

Erste öffentliche Version von Ford Triplog für Home Assistant.

Neu:
• Automatische Fahrterkennung über FordPass
• Speicherung aller Fahrten mit Start-/Zieladresse
• Distanz, Dauer und SOC-Verbrauch
• Gesamtkilometer, Gesamtdauer und Fahrtenzähler
• Binary Sensor "Trip Active"
• Unterstützung für FordPass-Fahrzeuge

Verbesserungen gegenüber RC2:
• Material Design Icons für alle Sensoren
• Kürzere und übersichtlichere Sensornamen
• Modernisierte binary\_sensor.py
• Optimierte Darstellung im Home Assistant Dashboard

Kompatibilität:
• Home Assistant 2026.x
• FordPass Integration erforderlich

Es wurden keine Änderungen an der Fahrtenlogik oder am Speicherformat vorgenommen.
Vorhandene Fahrtdaten bleiben vollständig kompatibel.

