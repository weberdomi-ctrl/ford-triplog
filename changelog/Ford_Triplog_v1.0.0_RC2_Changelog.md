# Ford Triplog v1.0.0 RC2

**Release Candidate 2**

## Neue Funktionen

-   Verbesserter Coordinator mit robusterer Fahrterkennung.
-   Automatische Aktualisierung der Gesamtstatistik nach jeder
    abgeschlossenen Fahrt.
-   Optimierte Verarbeitung der Fahrzeugdaten nach Zündung AUS.
-   Verbesserte Synchronisation zwischen Coordinator und
    Home-Assistant-Sensoren.

## Verbesserungen

-   Stabilere Ermittlung von Start- und Zieladresse.
-   Zuverlässigere Speicherung abgeschlossener Fahrten.
-   Sensoren aktualisieren sich nach einer Fahrt automatisch.
-   Vereinheitlichte Verarbeitung der Fahrtdaten.
-   Überarbeitete History- und Statistikverwaltung.
-   Verbesserte interne Logging-Ausgaben für die Fehlersuche.

## Fehlerbehebungen

-   Behoben: Trip Count wurde nicht erhöht.
-   Behoben: Total Distance blieb auf 0 km.
-   Behoben: Total Duration blieb auf 0 s.
-   Behoben: Total Energy Used wurde nicht korrekt berechnet.
-   Behoben: Statistik wurde nach dem Speichern einer Fahrt nicht
    aktualisiert.
-   Behoben: Fehlerhafte Verarbeitung der Fahrthistorie.
-   Behoben: RuntimeWarning „coroutine ... was never awaited" bei
    Sensor-Callbacks.
-   Behoben: RuntimeWarning „coroutine ... was never awaited" beim
    Binary Sensor.
-   Behoben: Aktualisierung der Sensoren nach abgeschlossener Fahrt.

## Bekannte Einschränkungen

-   Die Fahrstrecke basiert auf dem von FordPass gelieferten
    Kilometerstand.
-   Sehr kurze Fahrten können aufgrund der Aktualisierung des
    Kilometerstands durch FordPass leicht von der tatsächlich gefahrenen
    Strecke abweichen.
-   Die Endposition wird anhand der von FordPass gelieferten GPS-Daten
    bestimmt. Weitere Optimierungen der Stabilisierung sind geplant.

## Getestet mit

-   Home Assistant Core 2026.6.x
-   FordPass Home Assistant Integration
-   Ford Explorer EV (MEB)

## Ausblick auf v1.1.0

-   Ladehistorie
-   Automatische Erkennung von Ladepausen
-   Smart Trip Continuation
-   Zusammenführen von Fahrten mit kurzen Stopps
-   Speicherung von Ladeort, Ladedauer und geladener Energie
-   Erweiterte Statistiken
-   Konfigurierbare Zeitfenster über den Options Flow
