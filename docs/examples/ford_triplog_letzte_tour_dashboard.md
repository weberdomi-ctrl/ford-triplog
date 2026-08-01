{% set s = 'sensor.garage_ford_triplog_letzte_tour_ubersicht' %}
{% set timeline = state_attr(s, 'timeline') %}

# 🚗 Ford Triplog – Letzte Tour

## 📊 Zusammenfassung

- **{{ states(s) }}**
- 📏 Distanz: **{{ state_attr(s, 'distance_km') }} km**
- ⏱️ Gesamtdauer: **{{ state_attr(s, 'total_duration') }}**
- 🚗 Fahrzeit: **{{ state_attr(s, 'driving_duration') }}**
- ⏸️ Pausen: **{{ state_attr(s, 'pause_duration') }}**
- ⚡ Ladezeit: **{{ state_attr(s, 'charging_duration') }}**

---

## ⚡ Energie

- ⚡ Verbrauch: **{{ state_attr(s, 'energy_used_kwh') }} kWh**
- 🔋 Geladen: **{{ state_attr(s, 'energy_charged_kwh') }} kWh**
- ⚖️ Netto-Energiebilanz: **{{ state_attr(s, 'battery_energy_balance_kwh') }} kWh**
- 🔄 Gesamtenergiefluss: **{{ state_attr(s, 'total_energy_flow_kwh') }} kWh**

---

## 🔋 Batterie

- 🔋 Nutzbare Kapazität: **{{ state_attr(s, 'battery_capacity_kwh') }} kWh**
- 🟢 SOC Start: **{{ state_attr(s, 'start_soc') }} %**
- 🏁 SOC Ende: **{{ state_attr(s, 'end_soc') }} %**
- 📊 SOC Änderung: **{{ state_attr(s, 'soc_delta') }} %**
- ⚡ Batterieänderung: **{{ state_attr(s, 'battery_energy_delta_kwh') }} kWh**

---

## 📈 Analyse

- 🔻 SOC Verbrauch: **{{ state_attr(s, 'soc_used') }} %**
- 🔺 SOC Geladen: **{{ state_attr(s, 'soc_charged') }} %**
- 🔄 SOC Korrektur: **{{ state_attr(s, 'soc_adjustment') }} %**
- ⚡ SOC Korrektur: **{{ state_attr(s, 'soc_adjustment_kwh') }} kWh**
- 📈 Ø Verbrauch: **{{ state_attr(s, 'average_consumption_kwh_100km') }} kWh/100 km**

---

## 🕓 Timeline

{% for item in timeline %}

{% if item.type == "start" %}

### 🟢 {{ item.time_formatted }}
📍 **{{ item.location }}**

---

{% elif item.type == "trip" %}

### 🚗 {{ item.start_time_formatted }}–{{ item.end_time_formatted }}

⏱️ {{ item.duration }} · {{ item.distance_km | round(1) }} km

🔋 {{ item.start_soc | int }} → {{ item.end_soc | int }} %
(-{{ item.soc_used | int }} %)

⚡ {{ item.energy_used_kwh | round(1) }} kWh
{% if item.distance_km >= 3 %}
📈 {{ item.consumption_kwh_100km | round(1) }} kWh/100 km
{% endif %}

📍 {{ item.start_location }}
➡️ {{ item.end_location }}

---

{% elif item.type == "pause" %}

### ⏸️ {{ item.start_time_formatted }}

⏱️ {{ item.duration }}

📍 {{ item.location }}

---

{% elif item.type == "charge" %}

### ⚡ {{ item.start_time_formatted }}–{{ item.end_time_formatted }}

🔋 {{ item.start_soc | int }} → {{ item.end_soc | int }} %
(+{{ item.soc_added | int }} %)

⚡ {{ item.energy_charged_kwh | round(1) }} kWh

📍 {{ item.location }}

---

{% elif item.type == "end" %}

### 🏁 {{ item.time_formatted }}

📍 **{{ item.location }}**

{% endif %}

{% endfor %}
