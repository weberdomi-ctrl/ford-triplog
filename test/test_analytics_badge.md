# Ford Triplog Analytics Badge Test

## Home Assistant Analytics -- Installationen

[![Ford Triplog
usage](https://img.shields.io/badge/dynamic/json?style=for-the-badge&logo=home-assistant&logoColor=ccc&label=usage&suffix=%20installs&cacheSeconds=300&url=https://analytics.home-assistant.io/custom_integrations.json&query=$.ford_triplog.total)](https://analytics.home-assistant.io/)

## Rohdaten

Der Badge liest:

`https://analytics.home-assistant.io/custom_integrations.json`

mit der JSON-Abfrage:

`$.ford_triplog.total`

Falls Ford Triplog bereits in den Home-Assistant-Analytics-Daten
enthalten ist, sollte oben die gemeldete Anzahl der Installationen
erscheinen.
