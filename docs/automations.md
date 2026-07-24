# Automations

Ford Triplog provides native Home Assistant sensors that can be used in automations.

This page contains several practical examples that can be adapted to your own setup.

---

# Trip Completed Notification

Receive a notification whenever a trip is completed.

```yaml
alias: Ford Trip Completed
trigger:
  - platform: state
    entity_id: sensor.ford_triplog_last_distance
action:
  - service: notify.mobile_app_phone
    data:
      title: Trip Completed
      message: >
        Distance: {{ states('sensor.ford_triplog_last_distance') }} km

        Consumption: {{ states('sensor.ford_triplog_last_consumption') }} kWh/100 km
```

---

# Charging Finished Notification

Notify when a charging session is completed.

```yaml
alias: Charging Finished
trigger:
  - platform: state
    entity_id: sensor.ford_triplog_last_charge_end_time
action:
  - service: notify.mobile_app_phone
    data:
      title: Charging Finished
      message: >
        Battery:
        {{ states('sensor.ford_triplog_last_charge_start_soc') }}%

        →

        {{ states('sensor.ford_triplog_last_charge_end_soc') }}%
```

---

# Notify About High Consumption

Warn if the latest trip exceeded a defined consumption.

```yaml
alias: High Consumption
trigger:
  - platform: state
    entity_id: sensor.ford_triplog_last_consumption
condition:
  - condition: numeric_state
    entity_id: sensor.ford_triplog_last_consumption
    above: 22
action:
  - service: notify.mobile_app_phone
    data:
      message: >
        High consumption detected:
        {{ states('sensor.ford_triplog_last_consumption') }}
        kWh/100 km
```

---

# Weekly Driving Report

Create a weekly notification.

```yaml
alias: Weekly Trip Summary
trigger:
  - platform: time
    at: "18:00:00"
condition:
  - condition: time
    weekday:
      - sun
action:
  - service: notify.mobile_app_phone
    data:
      title: Weekly Statistics
      message: >
        Trips:
        {{ states('sensor.ford_triplog_trip_count') }}

        Distance:
        {{ states('sensor.ford_triplog_total_distance') }} km
```

---

# Charging Reminder

Example reminder if the battery remains below 20%.

```yaml
alias: Low Battery Reminder
trigger:
  - platform: numeric_state
    entity_id: sensor.ford_soc
    below: 20
action:
  - service: notify.mobile_app_phone
    data:
      message: Battery level is below 20%.
```

---


---

# Charging Station Notification

Notify when a public charging session has finished.

```yaml
alias: Charging Station Notification
trigger:
  - platform: state
    entity_id: sensor.ford_triplog_last_charge_end_time

condition:
  - condition: template
    value_template: >
      {{ states('sensor.ford_triplog_last_charging_station')
         not in ['unknown','unavailable',''] }}

action:
  - service: notify.mobile_app_phone
    data:
      title: Charging Completed
      message: >
        {{ states('sensor.ford_triplog_last_charging_station') }}

        Battery:
        {{ states('sensor.ford_triplog_last_charge_start_soc') }}%
        →
        {{ states('sensor.ford_triplog_last_charge_end_soc') }}%
```


# Logbook Entry

Add every completed trip to the Home Assistant Logbook.

```yaml
alias: Log Last Trip
trigger:
  - platform: state
    entity_id: sensor.ford_triplog_last_end_time
action:
  - service: logbook.log
    data:
      name: Ford Triplog
      message: >
        {{ states('sensor.ford_triplog_last_distance') }} km completed.
```

---

# Voice Announcement

Announce the end of a charging session on a media player.

```yaml
alias: Charging Voice Notification
trigger:
  - platform: state
    entity_id: sensor.ford_triplog_last_charge_end_time
action:
  - service: tts.speak
    target:
      entity_id: tts.home_assistant_cloud
    data:
      media_player_entity_id: media_player.living_room
      message: Charging has completed.
```

---

# Ideas

Ford Triplog sensors can be used for many other automations, including:

- Notify when arriving home
- Notify after long trips
- Track monthly driving distance
- Monitor average efficiency
- Create custom energy reports
- Trigger dashboards after charging
- Export trip data
- Integrate with voice assistants

---

# Tips

> [!TIP]
> Ford Triplog exposes standard Home Assistant entities.

This means every sensor can be used with:

- Automations
- Scripts
- Scenes
- Dashboards
- Template Sensors
- Voice Assistants

No additional integration is required.

---

# Next Step

Learn how Ford Triplog stores trips and charging sessions.

➡ **[Storage](storage.md)**