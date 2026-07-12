# Ford Triplog

A Home Assistant custom integration that automatically records trips for
Ford electric vehicles using the existing **FordPass Home Assistant
integration**.

> **Status:** v1.0.0 RC2

## Purpose

Ford Triplog automatically records your journeys and provides a clear
overview of:

-   Date and time
-   Start and destination address
-   Distance
-   Trip duration
-   State of Charge (SOC)
-   Estimated energy consumption

The collected information can be used as a convenient basis for travel
expense reports or for **manually transferring trips into a company
mileage log or other business systems**.

> **Note:** Ford Triplog is **not** a certified tax-compliant mileage
> log. It is intended as a personal trip log and documentation tool.

## Features

-   Automatic trip detection using ignition state
-   Start and destination addresses (reverse geocoding)
-   Distance calculation using the Ford odometer
-   Trip duration
-   SOC consumption
-   Estimated energy consumption
-   Trip history stored as JSON
-   Overall statistics
-   Home Assistant sensors
-   Active trip binary sensor

## Requirements

-   Home Assistant 2026.6.x or newer
-   FordPass Home Assistant integration
-   Supported Ford vehicle (tested with Ford Explorer EV)

## Installation

1.  Install and configure the FordPass integration.
2.  Copy `custom_components/ford_triplog` into
    `/config/custom_components/`.
3.  Restart Home Assistant.
4.  Add **Ford Triplog** via **Settings → Devices & Services → Add
    Integration**.
5.  Select the required FordPass entities:
    -   Ignition
    -   Odometer
    -   Tracker
    -   State of Charge (SOC)

## Included Sensors

-   Trip Count
-   Total Distance
-   Total Duration
-   Total Energy Used
-   Last Trip Distance
-   Last Trip Duration
-   Last Trip SOC Used
-   Last Trip Start Address
-   Last Trip End Address
-   Trip Active

## Storage

Trips are stored locally as JSON files. Statistics are updated
automatically after every completed trip.

## Roadmap

### v1.1.0

-   Smart Trip Continuation
-   Charging stop detection
-   Charging history
-   Configurable timing options
-   Dashboard
-   Extended statistics

## Compatibility

Tested:

-   Ford Explorer EV (MEB)

Wanted:

-   Ford Capri EV

## Feedback

Bug reports and feature requests are welcome via GitHub Issues.

## License

MIT License
