# Ford Triplog

A Home Assistant custom integration that automatically records trips for
Ford electric vehicles using the existing **FordPass Home Assistant
integration**.

> **Status:** v1.0.0 RC2

## Features

-   Automatic trip detection using ignition state
-   Start and destination addresses (reverse geocoding)
-   Distance calculation using the Ford odometer
-   Trip duration
-   State of Charge (SOC) consumption
-   Estimated energy consumption
-   Trip history stored as JSON
-   Overall statistics
-   Home Assistant sensors
-   Active trip binary sensor

## Requirements

-   Home Assistant
-   FordPass Home Assistant integration
-   Ford vehicle supported by the FordPass integration (tested with Ford
    Explorer EV)

## Installation

1.  Install the FordPass integration in Home Assistant.
2.  Copy the `custom_components/ford_triplog` folder into your Home
    Assistant configuration.
3.  Restart Home Assistant.
4.  Add **Ford Triplog** via **Settings → Devices & Services → Add
    Integration**.
5.  Select the required FordPass entities:
    -   Ignition
    -   Odometer
    -   Tracker
    -   State of Charge (SOC)

## Sensors

The integration provides, among others:

-   Trip Count
-   Total Distance
-   Total Duration
-   Total Energy Used
-   Last Trip Distance
-   Last Trip Duration
-   Last Trip SOC Used
-   Last Trip Start Address
-   Last Trip End Address
-   Trip Active (Binary Sensor)

## Storage

Trips are stored locally as JSON files. Statistics are generated
automatically after every completed trip.

## Roadmap

### Version 1.1.0

-   Charging history
-   Charging stop detection
-   Smart Trip Continuation
-   Pause detection
-   Configurable timing options
-   Extended statistics

## Compatibility

Currently tested with:

-   Ford Explorer EV (MEB)

Likely compatible:

-   Ford Capri EV (Tester wanted)

## Feedback

Bug reports and feature requests are welcome via GitHub Issues.

## License

MIT License
