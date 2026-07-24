# Ford Triplog Roadmap

## Version 1.0 -- Erste Veröffentlichung

- Grundlegende Trip-Erfassung
- Automatische Fahrt-Erkennung
- Speicherung von Start- und Endzeit
- GPS-Positionen
- Adressauflösung über OpenStreetMap
- Odometer
- SOC (State of Charge)
- Distanz und Fahrzeit
- Home-Assistant-Integration

## Version 1.1 -- Smart Trip

- Smart Trip eingeführt
- Kurze Stopps werden zu einer Fahrt zusammengefasst
- Konfigurierbarer Smart-Trip-Timeout
- Stabilere Trip-Erkennung
- Verbesserte Wiederherstellung nach einem Home-Assistant-Neustart

## Version 1.2 -- Statistiken und Sensoren

- Verbrauchsberechnung
- kWh/100 km
- Durchschnittsgeschwindigkeit
- Energieverbrauch
- Sensoren für die letzte Fahrt
- Gesamtstatistiken
- Verbesserte Recovery
- Stabilitätsverbesserungen

## Version 1.3 -- Trip und Charging

- Modernisiertes Charge-Modell
- Charge-ID
- Schema-Versionierung
- Erweiterte Metadaten
- Notizen und Tags
- Automatische Verknüpfung von Trip und Charge
- Gemeinsame Datenbasis für Fahrten und Ladevorgänge
- Verbesserte Recovery
- Optimierte History- und Cache-Verarbeitung

## Version 1.4 -- Smarte Ladeorte

- Automatische Erkennung öffentlicher Ladeorte
- OpenStreetMap-Overpass-Integration
- Länderbasierte Ladeort-Datenbanken
- Download und Import von Ladeort-Datenbanken
- Lokaler Geohash-Index für schnelle Ladeortsuche
- Betreiber
- Netzwerk
- Ladepunktname
- Ladeleistung
- Anzahl Ladepunkte
- Steckertypen
- Anzeige des Ladeorts statt nur der Adresse
- Ladeort-Sensoren und zusätzliche Attribute
- Verbesserte Recovery aktiver Ladevorgänge
- Vollständige Übersetzungen der Integration
- Architektur- und Konfigurationsdokumentation

# Geplant

## Version 1.5 -- Erweiterte FordPass-Ladedaten

### FordPass als primäre Datenquelle

- FordPass-Sensor „Letzter Ladevorgang“ als primäre Quelle für abgeschlossene Ladungen
- Übernahme der von FordPass gelieferten Start- und End-SOC-Werte
- Übernahme der tatsächlich geladenen Energie
- Übernahme von Ladebeginn und Ladeende
- Übernahme der Ladedauer
- Übernahme der hinzugefügten Reichweite
- Übernahme des Ladegerätetyps
- Übernahme von Leistungswerten, soweit verfügbar
- Weitere nutzbare FordPass-Ladeattribute

### Zusammenführung der Datenquellen

- FordPass-Ladeort als primäre Quelle
- Übernahme von Ladeortname, Netzwerk, Adresse und Koordinaten
- Lokale OpenStreetMap-Datenbank als Fallback, wenn FordPass keinen Ladeort liefert
- OpenStreetMap zur Ergänzung fehlender Metadaten
- FordPass-Daten werden nicht durch leere OSM-Werte überschrieben
- Plausibilitätsprüfung, damit der FordPass-Datensatz zur gerade abgeschlossenen Ladesession gehört
- Kennzeichnung der Datenquelle einzelner Werte, soweit sinnvoll

### Konfigurierbarer Heimladeort

- Eigener Name, zum Beispiel „Zuhause“
- Eingabe einer Adresse oder direkter Koordinaten
- Einmalige Umwandlung der Adresse in Koordinaten
- Konfigurierbarer Erkennungsradius
- Automatische Kennzeichnung von Heimladungen
- Anzeige des Heimladenamens statt nur der postalischen Adresse
- Grundlage für die spätere automatische Heimladekostenberechnung

### Ladeerkennung und Auswertung

- Zuverlässigere AC/DC-Erkennung
- Verbesserte Berechnung der durchschnittlichen Ladeleistung
- Vergleich von FordPass-Werten und eigenen Ford-Triplog-Messwerten
- Fehlende Werte weiterhin aus SOC und Batteriekapazität ableiten
- Erweiterte Sensoren und Attribute für den letzten Ladevorgang
- Feinschliff bei Ladeort- und Ladesessionsensoren

## Version 1.6 -- Statistikcenter

- Anzahl Fahrten
- Anzahl Ladevorgänge
- AC- und DC-Ladungen
- Durchschnittliche Fahrstrecke
- Durchschnittlicher Verbrauch
- Durchschnittliche Lademenge
- Durchschnittliche Ladezeit
- Durchschnittliche Ladeleistung
- Heimladen vs. öffentliches Laden
- Meistgenutzter Ladeanbieter
- Monatsstatistiken
- Jahresstatistiken
- Erweiterte Home-Assistant-Sensoren
- Dashboard-Karten und Auswertungen
- CSV-Export
- GPX-Export

## Version 1.7 -- Kostenmanagement und Wartung

### Öffentliches Laden

- Preis manuell ergänzen
- Preis pro kWh
- Gesamtpreis
- Startgebühren
- Parkgebühren
- Zahlungsmethode
- Kommentare

### Heimladen

- Automatische Erkennung anhand des konfigurierten Heimladeorts
- Automatische Kostenermittlung
- Konfigurierbare Stromtarife
- Saisonale Tarife für Sommer und Winter
- Optional Hoch- und Niedertarif
- Speicherung des verwendeten Tarifs im Ladeeintrag

### Auswertungen

- Ladekosten pro Monat
- Ladekosten pro Jahr
- Kosten pro 100 km
- Durchschnittlicher Strompreis
- Kosten nach Ladeanbieter
- Heimladen vs. öffentliches Laden
- Gesamte Stromkosten des Fahrzeugs

### Wartungsbereich

- Wartungsbereich in den Integrationsoptionen
- Vollständiges Neuberechnen der Statistiken
- Prüfung und Reparatur von Cache-Dateien
- Neuaufbau der letzten Trip- und Charge-Datensätze
- Weitere sichere Datenpflegefunktionen

## Version 1.8 -- Langzeitspeicherung und erweiterte Analyse

- Prüfung eines optionalen Datenbank-Backends
- JSON-Dateien bleiben der Standard für normale Installationen
- Optionale SQLite-Unterstützung für große Historien
- Schnellere Abfragen bei sehr vielen Fahrten und Ladevorgängen
- Erweiterte Langzeitstatistiken
- Verbesserte Filter- und Suchmöglichkeiten
- Vorbereitung komplexerer statistischer Analysen
- Performance-Optimierungen für lange Nutzungszeiträume

## Spätere Themen

- Mehrfahrzeug-Unterstützung
- Getrennte Historien und Statistiken pro Fahrzeug
- Gemeinsame Flottenübersicht
- Fahrzeugvergleich
- Optionale lokale Backup- und Exportfunktionen
- Interaktive Timeline aus Fahrten und Ladevorgängen

# Langfristige Vision

Ford Triplog soll sich von einer reinen Trip-Aufzeichnung zu einem
vollständigen digitalen Fahrtenbuch für Elektrofahrzeuge entwickeln.

Ziel ist eine lokale Home-Assistant-Lösung, die alle relevanten
Informationen rund um das Fahrzeug an einem Ort zusammenführt:

- Fahrten
- Ladevorgänge
- Ladeorte
- Verbrauch
- Kosten
- Statistiken
- Historie
- Gemeinsame Timeline von Fahrten und Ladungen

So entsteht eine vollständige Dokumentation des Fahrzeugs -- vom Start
der Fahrt bis zu den gesamten Betriebskosten.
