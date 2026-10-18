# Ford Triplog – Einfaches Dashboard einrichten

Diese Anleitung richtet sich an Einsteiger, die Fahrzeugdaten, die letzte Ladung, Ladekosten und die Ladehistorie in Home Assistant anzeigen möchten.

**Wichtig:** Ford Triplog erstellt kein Dashboard und keinen Seitenleisten-Eintrag automatisch. Die Vorlage verwendet ausschliesslich Home-Assistant-Standardkarten; zusätzliche HACS-Karten sind nicht erforderlich.

## 1. Voraussetzungen

- Ford Triplog ist eingerichtet und liefert bereits Daten.
- Für Batteriestand, Reichweite und Kilometerstand sind passende Entitäten aus deiner Fahrzeug-Integration vorhanden (z. B. FordPass). Diese drei Werte stammen nicht zwangsläufig aus Ford Triplog.
- Du kannst Dashboards in Home Assistant bearbeiten.

## 2. Entity-IDs ermitteln

1. Öffne **Entwicklerwerkzeuge → Zustände**.
2. Suche nach `ford_triplog` und notiere die tatsächlichen Entity-IDs für:
   - Letzter Ladevorgang (Attribut `cost_total`, `energy_added_kwh`)
   - Charging History (Attribut `charges`)
   - Letzte Tour / Tour-Übersicht (Attribut `distance_km`)
3. Suche die Fahrzeug-Entitäten für Batteriestand, Reichweite und Kilometerstand.
4. Öffne einen Sensor und prüfe seine **Attribute**. So erkennst du, ob du den richtigen Sensor gewählt hast.

**Achtung:** Die in der Vorlage verwendeten IDs mit `sensor.garage_...` sind Beispiele aus der Dokumentation. Der Präfix hängt von deiner Installation ab. IDs mit `MEIN_AUTO_...` sind Platzhalter und müssen ersetzt werden.

## 3. Dashboard erstellen

1. Öffne in Home Assistant **Einstellungen → Dashboards**.
2. Erstelle ein **neues Dashboard** und öffne es.
3. Wechsle über das Menü oben rechts in den **Bearbeitungsmodus**.
4. Öffne den **Raw-Konfigurationseditor** (je nach Home-Assistant-Version unter dem Drei-Punkte-Menü).
5. Kopiere den gesamten Inhalt von [`ford_triplog_starter_dashboard.yaml`](ford_triplog_starter_dashboard.yaml) in den Editor. Bei einem neu erstellten Dashboard kannst du den vorhandenen Beispielinhalt ersetzen.
6. Ersetze alle Entity-IDs durch deine tatsächlichen IDs:
   - `sensor.MEIN_AUTO_BATTERIESTAND`
   - `sensor.MEIN_AUTO_REICHWEITE`
   - `sensor.MEIN_AUTO_KILOMETERSTAND`
   - `sensor.garage_ford_triplog_letzter_ladevorgang`
   - `sensor.garage_ford_triplog_charging_history`
   - `sensor.garage_ford_triplog_letzte_tour_ubersicht`
7. Speichere das Dashboard.

Falls du ein bereits benutztes Dashboard hast, **nicht dessen komplette Konfiguration ersetzen**. Erstelle besser ein separates Dashboard für Ford Triplog.

## 4. Was zeigt die Vorlage?

- **Fahrzeug:** aktueller Batteriestand, Reichweite und Kilometerstand über die vorhandenen Fahrzeug-Sensoren.
- **Letzte Ladung:** Ladeort, Start-/End-SOC, Energie, Gesamtkosten und effektiver Preis je kWh.
- **Ladehistorie:** Zusammenfassung und einzelne Ladevorgänge des **aktuell im History-Sensor ausgewählten Tages**.
- **Letzte Tour:** Distanz, Dauer und Energieverbrauch der letzten Tour.

Die History-Sensoren liefern nicht automatisch eine beliebig lange Liste aller Ladevorgänge. Für die Datumsauswahl siehe das bestehende Beispiel [`ford_triplog_history_datumauswahl_dashboard.md`](ford_triplog_history_datumauswahl_dashboard.md). Die Vorlage hier zeigt die Daten des bereits ausgewählten Tages.

## 5. Dynamische Ladekosten prüfen

1. Öffne **Entwicklerwerkzeuge → Zustände** und den Sensor **Letzter Ladevorgang**.
2. Prüfe die Attribute `start_time`, `end_time`, `energy_added_kwh`, `cost_total`, `currency`, `effective_price_per_kwh` und gegebenenfalls `cost_source`.
3. Vergleiche den berechneten Gesamtpreis mit der Abrechnung deines Stromanbieters. Bei dynamischen Tarifen kann der effektive Preis vom Strompreis zum Ladeende abweichen.
4. Für einen Fehlerbericht genügen zunächst die relevanten Attribute sowie die Information, welche Preis-Entität verwendet wurde. Bitte **keine komplette SQLite-Datenbank öffentlich hochladen**: Sie kann Fahrten, Standorte und andere persönliche Daten enthalten. Zugangstoken, Signaturen und persönliche Adressen vor dem Teilen entfernen.

## 6. Wenn nichts angezeigt wird

- **„Entität nicht verfügbar“:** Entity-ID in der YAML überprüfen.
- **Keine letzte Ladung:** Prüfen, ob Ford Triplog schon einen Ladevorgang aufgezeichnet hat.
- **Keine Ladehistorie:** Den ausgewählten History-Tag prüfen; eventuell existiert an diesem Tag keine Ladung.
- **Fahrzeugwerte fehlen:** Die drei Fahrzeug-Entitäten aus deiner Ford-/Fahrzeug-Integration einsetzen.

## Weitere Beispiele

Die umfangreicheren Vorlagen befinden sich unter [docs/examples](https://github.com/weberdomi-ctrl/ford-triplog/tree/main/docs/examples), unter anderem für die letzte Ladung, Ladehistorie, Fahrten und Routen.
