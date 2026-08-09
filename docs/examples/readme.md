# Dashboard Examples

The following examples can be copied directly into Home Assistant dashboard cards.

Before using them, adjust the entity IDs to match your installation.

## Current dashboards

- `ford_triplog_letzte_tour_dashboard.md` – Last Journey Dashboard
- `ford_triplog_letzte_ladung_dashboard.md` – Last Charging Dashboard

## History dashboards

The History dashboards use the shared Ford Triplog History date selection. Changing the selected date updates the available Route, Journey, Charging and Receipt history for that day.

- `ford_triplog_history_datumauswahl_dashboard.md` – History date selection
- `ford_triplog_history_tour_dashboard.md` – Journey history for the selected day
- `ford_triplog_history_tourmap_dashboard.md` – Route map for the selected day
- `ford_triplog_history_ladungen_dashboard.md` – Charging history for the selected day
- `ford_triplog_history_ladebelege_dashboard.md` – Charging receipts for the selected day

The route map can be configured to remain hidden on days without route data. Charging-only days can still be selected and displayed.

## Required custom cards

The History route map requires the following custom cards, available through HACS:

- **Google Map Card** – displays the recorded route on the map
- **Config Template Card** – refreshes the map correctly when the selected History date changes

Make sure both custom cards are installed and available in Home Assistant before using the History route map example.
