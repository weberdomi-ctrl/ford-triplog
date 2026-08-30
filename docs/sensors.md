# Sensors

Ford Triplog provides a comprehensive set of native Home Assistant
sensors.

The available entities are automatically created after the integration
has been configured.

They provide real-time information, the latest recorded trip and
charging session, as well as lifetime statistics.

------------------------------------------------------------------------

# Overview

Ford Triplog sensors include the following main categories:

-   Current Journey
-   Last Journey
-   Journey History
-   Last Trip
-   Trip / route history
-   Last Charging Session
-   Charging History
-   Statistics
-   Status

All sensors update automatically.

------------------------------------------------------------------------

# Last Journey

The Last Journey sensors summarize an entire journey consisting of one
or more trips and charging sessions.

## Last Journey

    Last Journey

Timestamp sensor representing the completion time of the latest journey.

Attributes include:

-   Journey ID
-   Start and destination
-   Journey date
-   Distance
-   Driving duration
-   Charging duration
-   Total duration
-   Energy used
-   Energy charged
-   Average consumption
-   Trip IDs
-   Charging session IDs
-   Battery energy balance
-   Battery energy delta
-   Total battery energy flow
-   Charging cost summary
-   Average charging price
-   Currency

------------------------------------------------------------------------

## Last Journey Overview

    Last Journey Overview

Dashboard-oriented summary sensor.

State example:

    315 km · 5 h 42 min

Attributes include:

-   Start
-   Destination
-   Total distance
-   Driving duration
-   Pause duration
-   Charging duration
-   Total duration
-   Number of trips
-   Number of charging sessions
-   Energy used
-   Energy charged
-   Average consumption
-   Timeline
-   Journey charging costs
-   Average charging price
-   Battery energy balance

The timeline contains ordered entries for:

-   Start
-   Trips
-   Pauses
-   Charging sessions
-   Destination

------------------------------------------------------------------------


# History Sensors

Ford Triplog provides history-oriented sensors for dashboard use and
record review.

## Journey History

The Journey History sensor provides the Journey data for the selected
history date.

Depending on the recorded data, attributes can include:

-   Trips
-   Pauses
-   Charging sessions
-   Journey totals
-   Pause category
-   Pause notes
-   Pause costs
-   Pause receipts

Pause receipts can therefore be displayed in dedicated Home Assistant
Markdown cards together with pause duration and location.

------------------------------------------------------------------------

## Charging History

The Charging History sensor exposes recorded charging sessions for
history and dashboard presentation.

Charging entries can include receipt metadata and receipt URLs for
authenticated dashboard access.

------------------------------------------------------------------------

## Route / Trip History

Route history sensors expose stored trip and GPS route information used
by dashboard maps and history views.

------------------------------------------------------------------------

# Last Trip

The Last Trip sensors provide information about the most recently
completed individual Trip.

## Distance

    Last Trip Distance

Displays the travelled distance.

Example:

    42.6 km

------------------------------------------------------------------------

## Duration

    Last Trip Duration

Displays the total driving time.

Example:

    00:37:15

------------------------------------------------------------------------

## Average Speed

    Last Trip Average Speed

Calculated from:

    Distance / Driving Time

Example:

    68 km/h

------------------------------------------------------------------------

## Start State of Charge

    Last Trip Start SOC

Example:

    82 %

------------------------------------------------------------------------

## End State of Charge

    Last Trip End SOC

Example:

    64 %

------------------------------------------------------------------------

## SOC Used

    Last Trip SOC Used

Example:

    18 %

------------------------------------------------------------------------

## Estimated Energy Consumption

    Last Trip Energy

Estimated using the configured usable battery capacity.

Example:

    14.2 kWh

------------------------------------------------------------------------

## Average Consumption

    Last Trip Consumption

Example:

    16.8 kWh/100 km

------------------------------------------------------------------------

## Start Time

    Last Trip Started

Timestamp of the trip start.

------------------------------------------------------------------------

## End Time

    Last Trip Finished

Timestamp of the completed trip.

------------------------------------------------------------------------

# Last Charging Session

These sensors describe the latest completed charging session.

------------------------------------------------------------------------

## Charging Duration

    Last Charging Duration

Example:

    01:14:32

------------------------------------------------------------------------

## Start State of Charge

    Last Charging Start SOC

------------------------------------------------------------------------

## End State of Charge

    Last Charging End SOC

------------------------------------------------------------------------

## SOC Gained

    Last Charging SOC Gained

Example:

    42 %

------------------------------------------------------------------------

## Charged Energy

    Last Charged Energy

Displays the stored energy added during the latest completed charging
session. Depending on the available vehicle source data, this can come from
final Ford charging-session information or from Ford Triplog's stored
charging calculation.

Example:

    33.2 kWh

------------------------------------------------------------------------

## Charging Location

    Last Charging Location

Example:

    IONITY Neuenkirch

------------------------------------------------------------------------

## Charging Provider

    Last Charging Provider

Example:

    IONITY

------------------------------------------------------------------------

## Charging Network

    Last Charging Network

Example:

    IONITY

------------------------------------------------------------------------

# Lifetime Statistics

Ford Triplog continuously updates lifetime statistics.

------------------------------------------------------------------------

## Total Trips

    Total Trips

Displays the total number of completed trips.

------------------------------------------------------------------------

## Total Distance

    Total Distance

Displays the cumulative distance.

------------------------------------------------------------------------

## Total Driving Time

    Total Driving Time

Displays the accumulated driving time.

------------------------------------------------------------------------

## Total Energy Consumption

    Total Energy Consumption

Estimated total energy used for driving.

------------------------------------------------------------------------

## Average Consumption

    Average Consumption

Average lifetime efficiency.

Example:

    17.4 kWh/100 km

------------------------------------------------------------------------

## Total Charging Sessions

    Total Charging Sessions

Displays the number of recorded charging sessions.

------------------------------------------------------------------------

# Status Sensors

Ford Triplog provides a status entity for active Trip detection.

## Current Trip Active

    Current Trip Active

Indicates whether Ford Triplog currently considers a Trip active. The entity
availability follows the Ford Triplog coordinator and its listener is
registered and removed with the Home Assistant entity lifecycle.

Additional operational information is exposed through the relevant Trip,
Journey, Route and charging sensors rather than separate status entities.

------------------------------------------------------------------------

# Entity Naming

Ford Triplog follows Home Assistant naming conventions.

Example:

    sensor.ford_triplog_last_trip_distance

This makes entities easy to identify in dashboards, automations and
templates.

------------------------------------------------------------------------

# Updating

All sensors update automatically.

Typical update events include:

-   Vehicle movement
-   Trip completion
-   Charging completion
-   Configuration changes
-   Home Assistant restart

No manual refresh is required.

------------------------------------------------------------------------

# Dashboard Usage

The sensors are designed to work directly with native Home Assistant
dashboard cards.

Typical cards include:

-   Entity Card
-   Tile Card
-   Statistics Card
-   History Graph
-   Gauge
-   Markdown Card

Example dashboards are available in:

    docs/dashboard.md

------------------------------------------------------------------------

# Automations

Every sensor can be used in Home Assistant automations.

Examples:

-   Notify when charging has finished.
-   Notify when arriving home.
-   Display the last trip on a dashboard.
-   Track monthly driving distance.
-   Use stored charging and Journey cost data in automations.

Example automations are provided in:

    docs/automation_examples.md

------------------------------------------------------------------------

# Availability

Previously recorded Trips, charging sessions, Journeys and Routes remain
accessible after Home Assistant or integration restarts because persistent
Ford Triplog data is stored locally in SQLite.

During startup, source integrations can temporarily expose `unknown` or
`unavailable` values. Ford Triplog normalizes these states instead of
treating them as numeric values.

------------------------------------------------------------------------

# Future Sensors

Future releases will introduce additional entities, including:

-   Monthly statistics
-   Yearly statistics
-   Vehicle usage summaries
-   Multi-vehicle sensors

The existing entity names will remain stable whenever possible to avoid
breaking dashboards and automations.
