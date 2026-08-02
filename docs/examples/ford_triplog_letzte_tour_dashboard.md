
{% set s = 'sensor.garage_ford_triplog_letzte_tour_ubersicht' %}
{% set timeline = state_attr(s, 'timeline') or [] %}

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

## 💰 Ladekosten

{% set currency = state_attr(s, 'currency') or '' %}
{% set total_cost = state_attr(s, 'charging_cost_total') | float(0) %}
{% set energy_cost = state_attr(s, 'charging_energy_cost') | float(0) %}
{% set additional_cost = state_attr(s, 'charging_additional_cost') | float(0) %}
{% set average_price = state_attr(s, 'average_charging_price_per_kwh') | float(0) %}

- 💳 Gesamtkosten: **{{ total_cost | round(2) }} {{ currency }}**
- ⚡ Energiekosten: **{{ energy_cost | round(2) }} {{ currency }}**
- ➕ Zusatzkosten: **{{ additional_cost | round(2) }} {{ currency }}**
- 📊 Ø Ladepreis: **{{ average_price | round(4) }} {{ currency }}/kWh**

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

⏱️ {{ item.duration }} · {{ item.distance_km | float(0) | round(1) }} km

{% if item.start_soc is defined and item.end_soc is defined %}
🔋 {{ item.start_soc | int }} → {{ item.end_soc | int }} %
{% if item.soc_used is defined %}
(-{{ item.soc_used | int }} %)
{% endif %}
{% endif %}

{% if item.energy_used_kwh is defined %}
⚡ {{ item.energy_used_kwh | float(0) | round(1) }} kWh
{% endif %}

{% if item.distance_km | float(0) >= 3
      and item.consumption_kwh_100km is defined %}
📈 {{ item.consumption_kwh_100km | float(0) | round(1) }} kWh/100 km
{% endif %}

📍 {{ item.start_location }}
➡️ {{ item.end_location }}

---

{% elif item.type == "pause" %}

### ⏸️ {{ item.start_time_formatted }}

⏱️ {{ item.duration }}

{% if item.title is defined and item.title %}
{% set category = item.category | default('', true) %}
{% if category == 'food' %}
🍽️ **{{ item.title }}**
{% elif category == 'coffee' %}
☕ **{{ item.title }}**
{% elif category == 'shopping' %}
🛒 **{{ item.title }}**
{% elif category == 'sightseeing' %}
📸 **{{ item.title }}**
{% elif category == 'hotel' %}
🏨 **{{ item.title }}**
{% elif category == 'work' %}
💼 **{{ item.title }}**
{% elif category == 'break' %}
🪑 **{{ item.title }}**
{% else %}
📍 **{{ item.title }}**
{% endif %}
{% endif %}

{% if item.category is defined and item.category %}
{% if item.category == 'food' %}
🏷️ Essen
{% elif item.category == 'coffee' %}
🏷️ Kaffee
{% elif item.category == 'shopping' %}
🏷️ Einkauf
{% elif item.category == 'sightseeing' %}
🏷️ Besichtigung
{% elif item.category == 'hotel' %}
🏷️ Übernachtung
{% elif item.category == 'work' %}
🏷️ Arbeit
{% elif item.category == 'break' %}
🏷️ Pause
{% elif item.category == 'other' %}
🏷️ Sonstiges
{% else %}
🏷️ {{ item.category }}
{% endif %}
{% endif %}

{% if item.location is defined and item.location %}
📍 {{ item.location }}
{% endif %}

{% if item.note is defined and item.note %}
📝 {{ item.note }}
{% endif %}

{% if item.soc_start is defined and item.soc_end is defined %}
🔋 {{ item.soc_start | int }} → {{ item.soc_end | int }} %
{% if item.soc_delta is defined %}
({% if item.soc_delta | float(0) > 0 %}+{% endif %}{{ item.soc_delta | float(0) | round(1) }} %)
{% endif %}
{% endif %}

{% if item.energy_delta_kwh is defined %}
⚡ {% if item.energy_delta_kwh | float(0) > 0 %}+{% endif %}{{ item.energy_delta_kwh | float(0) | round(2) }} kWh
{% endif %}

{% if item.cost_total is defined %}
💰 {{ item.cost_total | float(0) | round(2) }} {{ item.currency | default('CHF', true) }}
{% endif %}

{% if item.edited | default(false) %}
✏️ Manuell ergänzt
{% endif %}

---

{% elif item.type == "charge" %}

### ⚡ {{ item.start_time_formatted }}–{{ item.end_time_formatted }}

{% if item.arrival_buffer_seconds | default(0) | int > 0 %}
🚗 Ankunft: {{ item.arrival_buffer }}
{% endif %}

⏱️ {{ item.duration }}

{% if item.departure_buffer_seconds | default(0) | int > 0 %}
🚙 Abfahrt: {{ item.departure_buffer }}
{% endif %}

{% if item.total_stop_duration_seconds | default(0) | int > 0 %}
🅿️ Aufenthalt: {{ item.total_stop_duration }}
{% endif %}

{% if item.start_soc is defined and item.end_soc is defined %}
🔋 {{ item.start_soc | int }} → {{ item.end_soc | int }} %
{% if item.soc_added is defined %}
(+{{ item.soc_added | int }} %)
{% endif %}
{% endif %}

{% if item.energy_charged_kwh is defined %}
⚡ Im Fahrzeug: **{{ item.energy_charged_kwh | float(0) | round(2) }} kWh**
{% endif %}

{% if item.energy_billed_kwh is defined %}
🧾 Abgerechnet: **{{ item.energy_billed_kwh | float(0) | round(2) }} kWh**
{% endif %}

{% if item.cost_total is defined %}
💰 Kosten: **{{ item.cost_total | float(0) | round(2) }} {{ item.currency | default('', true) }}**
{% endif %}

{% if item.energy_price_per_kwh is defined %}
📊 Energiepreis: **{{ item.energy_price_per_kwh | float(0) | round(4) }} {{ item.currency | default('', true) }}/kWh**
{% endif %}

{% if item.effective_price_per_kwh is defined
      and item.energy_price_per_kwh is defined
      and item.effective_price_per_kwh != item.energy_price_per_kwh %}
💳 Effektiver Preis: **{{ item.effective_price_per_kwh | float(0) | round(4) }} {{ item.currency | default('', true) }}/kWh**
{% endif %}

{% if item.cost_source is defined %}
🗂️ Quelle: **{{ item.cost_source }}**
{% endif %}

{% if item.location is defined and item.location %}
📍 {{ item.location }}
{% endif %}

---

{% elif item.type == "end" %}

### 🏁 {{ item.time_formatted }}

📍 **{{ item.location }}**

{% endif %}

{% endfor %}
```
