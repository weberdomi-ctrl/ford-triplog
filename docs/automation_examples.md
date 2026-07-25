# Automation Examples

Ford Triplog exposes native Home Assistant entities that can be used in automations.

The following examples demonstrate common automation scenarios. They can be adapted to your own installation by replacing the example entity IDs with your actual entities.

---

# Charging Finished Notification

Receive a notification whenever a charging session has completed.

```yaml
alias: Ford Triplog - Charging Finished

trigger:
  - platform: state
    entity_id: binary_sensor.ford_triplog_charging_active
    from: "on"
    to: "off"

action:
  - service: notify.mobile_app_phone
    data:
      title: Charging Finished
      message: >
        Your vehicle has finished charging.
```

---

# Vehicle Arrived Home

Trigger an automation when the vehicle enters the Home zone.

```yaml
alias: Ford Triplog - Vehicle Arrived Home

trigger:
  - platform: zone
    entity_id: device_tracker.ford_explorer
    zone: zone.home
    event: enter

action:
  - service: notify.mobile_app_phone
    data:
      title: Vehicle
      message: Vehicle arrived home.
```

---

# Vehicle Left Home

```yaml
alias: Ford Triplog - Vehicle Left Home

trigger:
  - platform: zone
    entity_id: device_tracker.ford_explorer
    zone: zone.home
    event: leave

action:
  - service: notify.mobile_app_phone
    data:
      message: Vehicle left home.
```

---

# Notify After Long Trip

Notify when the latest trip exceeds a certain distance.

```yaml
alias: Ford Triplog - Long Trip

trigger:
  - platform: state
    entity_id: sensor.ford_triplog_last_trip_distance

condition:
  - condition: numeric_state
    entity_id: sensor.ford_triplog_last_trip_distance
    above: 300

action:
  - service: notify.mobile_app_phone
    data:
      message: >
        You completed a trip longer than 300 km.
```

---

# Low Battery Notification

Notify when the battery level becomes low.

```yaml
alias: Ford Triplog - Low Battery

trigger:
  - platform: numeric_state
    entity_id: sensor.vehicle_soc
    below: 15

action:
  - service: notify.mobile_app_phone
    data:
      title: Battery Warning
      message: Battery level is below 15%.
```

---

# Charging Started

```yaml
alias: Ford Triplog - Charging Started

trigger:
  - platform: state
    entity_id: binary_sensor.ford_triplog_charging_active
    to: "on"

action:
  - service: notify.mobile_app_phone
    data:
      message: Charging has started.
```

---

# Charging Location Announcement

Inform the user where the vehicle has been charged.

```yaml
alias: Ford Triplog - Charging Location

trigger:
  - platform: state
    entity_id: binary_sensor.ford_triplog_charging_active
    from: "on"
    to: "off"

action:
  - service: notify.mobile_app_phone
    data:
      title: Charging Completed
      message: >
        Location:
        {{ states('sensor.ford_triplog_last_charging_location') }}
```

---

# Daily Driving Summary

Send a summary every evening.

```yaml
alias: Ford Triplog - Daily Summary

trigger:
  - platform: time
    at: "20:00:00"

action:
  - service: notify.mobile_app_phone
    data:
      title: Daily Driving Summary
      message: >
        Distance:
        {{ states('sensor.ford_triplog_total_distance') }}

        Trips:
        {{ states('sensor.ford_triplog_total_trips') }}
```

---

# Dashboard Refresh

Force a dashboard navigation when a trip finishes.

```yaml
alias: Ford Triplog - Refresh Dashboard

trigger:
  - platform: state
    entity_id: sensor.ford_triplog_last_trip_finished

action:
  - service: browser_mod.refresh
```

This example requires Browser Mod.

---

# Home Assistant Energy Dashboard

Use the estimated charged energy sensor inside the Home Assistant Energy Dashboard.

Recommended entities:

- Total Charged Energy
- Last Charged Energy

These values can be used together with other Home Assistant energy sensors.

---

# Example Conditions

Common conditions include:

```yaml
condition:
  - condition: state
    entity_id: person.dominik
    state: home
```

```yaml
condition:
  - condition: sun
    after: sunset
```

```yaml
condition:
  - condition: numeric_state
    entity_id: sensor.vehicle_soc
    below: 20
```

---

# Example Triggers

Typical Ford Triplog triggers include:

- Last trip updated
- Charging started
- Charging finished
- Vehicle arrived home
- Vehicle left home
- Statistics changed

---

# Ideas

Ford Triplog can be used to automate many vehicle-related tasks.

Examples include:

- Turn on exterior lighting when arriving home.
- Open the garage door automatically.
- Notify when charging has completed.
- Record monthly driving distance.
- Display charging history on a dashboard.
- Create voice announcements.
- Log vehicle usage statistics.
- Trigger energy management automations.

---

# Future Examples

Future documentation will include complete automation packages for:

- Home charging management
- Dynamic electricity tariffs
- Charging cost calculations
- Smart charging schedules
- Dashboard packages
- Monthly reports
- Vehicle maintenance reminders

These examples will use only stable Ford Triplog entities to ensure compatibility across future releases.