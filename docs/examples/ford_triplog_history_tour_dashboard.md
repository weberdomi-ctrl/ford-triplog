  {% set s = 'sensor.garage_ford_triplog_journey_history' %}

  {% set timeline = state_attr(s, 'timeline') or [] %}


  {% set journey_date_raw = state_attr(s, 'date') %}


  {% if journey_date_raw not in [none, '', 'unknown', 'unavailable'] %}
    {% set dt = journey_date_raw | as_datetime | as_local %}
    {% set journey_date = dt.timestamp() | timestamp_custom('%d.%m.%Y') %}
  {% else %}
    {% set journey_date = '—' %}
  {% endif %}


  # 🚗 Ford Triplog – Tour History


  ## 📅 Datum: **{{ journey_date }}**


  {% if state_attr(s, 'journey_count') | int(0) == 0 %}


  ## Keine Tour vorhanden


  Für den ausgewählten Tag wurde keine abgeschlossene Journey gefunden.


  {% else %}


  ## 📊 Zusammenfassung


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


  {% set item_type = item.get('type', '') %}


  {% if item_type == 'start' %}


  ### 🟢 {{ journey_date }} · {{ item.get('time_formatted', '—') }}


  📍 **{{ item.get('location', 'Unbekannter Ort') }}**


  ---


  {% elif item_type == 'trip' %}


  ### 🚗 {{ journey_date }} · {{ item.get('start_time_formatted', '—') }}–{{ item.get('end_time_formatted', '—') }}


  ⏱️ {{ item.get('duration', '—') }} · {{ item.get('distance_km', 0) | float(0) | round(1) }} km


  {% if item.get('start_soc') is not none and item.get('end_soc') is not none %}

  🔋 {{ item.get('start_soc') | int }} → {{ item.get('end_soc') | int }} %

  {% if item.get('soc_used') is not none %}

  (-{{ item.get('soc_used') | int }} %)

  {% endif %}

  {% endif %}


  {% if item.get('energy_used_kwh') is not none %}

  ⚡ {{ item.get('energy_used_kwh') | float(0) | round(1) }} kWh

  {% endif %}


  {% if item.get('distance_km', 0) | float(0) >= 3
  and item.get('consumption_kwh_100km') is not none %}

  📈 {{ item.get('consumption_kwh_100km') | float(0) | round(1) }} kWh/100 km

  {% endif %}


  📍 {{ item.get('start_location', 'Unbekannter Startort') }}

  ➡️ {{ item.get('end_location', 'Unbekannter Zielort') }}


  ---


  {% elif item_type == 'pause' %}


  ### ⏸️ {{ journey_date }} · {{ item.get('start_time_formatted', '—') }}


  ⏱️ {{ item.get('duration', '—') }}


  {% set category = item.get('category', '') %}

  {% set title = item.get('title', '') %}

  {% set location = item.get('location', '') %}

  {% set note = item.get('note', '') %}


  {% if category %}

  {% if category == 'food' %}

  🏷️ Essen

  {% elif category == 'coffee' %}

  🏷️ Kaffee

  {% elif category == 'shopping' %}

  🏷️ Einkauf

  {% elif category == 'sightseeing' %}

  🏷️ Besichtigung

  {% elif category == 'hotel' %}

  🏷️ Übernachtung

  {% elif category == 'work' %}

  🏷️ Arbeit

  {% elif category == 'break' %}

  🏷️ Pause

  {% elif category == 'other' %}

  🏷️ Sonstiges

  {% else %}

  🏷️ {{ category }}

  {% endif %}

  {% endif %}


  {% if title %}

  📝 **{{ title }}**

  {% endif %}


  {% if location %}

  📍 {{ location }}

  {% endif %}


  {% if note %}

  🗒️ {{ note }}

  {% endif %}


  {% if item.get('soc_start') is not none and item.get('soc_end') is not none %}

  🔋 {{ item.get('soc_start') | int }} → {{ item.get('soc_end') | int }} %

  {% if item.get('soc_delta') is not none %}

  ({% if item.get('soc_delta') | float(0) > 0 %}+{% endif %}{{ item.get('soc_delta') | int }} %)

  {% endif %}

  {% endif %}


  {% if item.get('battery_energy_change_kwh') is not none %}

  ⚡ Batterie: **{% if item.get('battery_energy_change_kwh') | float(0) > 0 %}+{% endif %}{{ item.get('battery_energy_change_kwh') | float(0) | round(2) }} kWh**

  {% endif %}


  {% if item.get('cost_total') is not none %}

  💰 Kosten: **{{ item.get('cost_total') | float(0) | round(2) }} {{ item.get('currency') or 'CHF' }}**

  {% endif %}


  {% if item.get('edited', false) %}

  ✏️ Manuell ergänzt

  {% endif %}


  ---


  {% elif item_type == 'charge' %}


  ### ⚡ {{ journey_date }} · {{ item.get('start_time_formatted', '—') }}–{{ item.get('end_time_formatted', '—') }}


  {% if item.get('arrival_buffer_seconds', 0) | int > 0 %}

  🚗 Ankunft: {{ item.get('arrival_buffer', '—') }}

  {% endif %}


  ⏱️ {{ item.get('duration', '—') }}


  {% if item.get('departure_buffer_seconds', 0) | int > 0 %}

  🚙 Abfahrt: {{ item.get('departure_buffer', '—') }}

  {% endif %}


  {% if item.get('total_stop_duration_seconds', 0) | int > 0 %}

  🅿️ Aufenthalt: {{ item.get('total_stop_duration', '—') }}

  {% endif %}


  {% if item.get('start_soc') is not none and item.get('end_soc') is not none %}

  🔋 {{ item.get('start_soc') | int }} → {{ item.get('end_soc') | int }} %

  {% if item.get('soc_added') is not none %}

  (+{{ item.get('soc_added') | int }} %)

  {% endif %}

  {% endif %}


  {% if item.get('energy_charged_kwh') is not none %}

  ⚡ Im Fahrzeug: **{{ item.get('energy_charged_kwh') | float(0) | round(2) }} kWh**

  {% endif %}


  {% if item.get('energy_billed_kwh') is not none %}

  🧾 Abgerechnet: **{{ item.get('energy_billed_kwh') | float(0) | round(2) }} kWh**

  {% endif %}


  {% if item.get('cost_total') is not none %}

  💰 Kosten: **{{ item.get('cost_total') | float(0) | round(2) }} {{ item.get('currency', '') }}**

  {% endif %}


  {% if item.get('energy_price_per_kwh') is not none %}

  📊 Energiepreis: **{{ item.get('energy_price_per_kwh') | float(0) | round(4) }} {{ item.get('currency', '') }}/kWh**

  {% endif %}


  {% if item.get('effective_price_per_kwh') is not none
  and item.get('energy_price_per_kwh') is not none
  and item.get('effective_price_per_kwh') != item.get('energy_price_per_kwh') %}

  💳 Effektiver Preis: **{{ item.get('effective_price_per_kwh') | float(0) | round(4) }} {{ item.get('currency', '') }}/kWh**

  {% endif %}


  {% if item.get('cost_source') %}

  🗂️ Quelle: **{{ item.get('cost_source') }}**

  {% endif %}


  {% if item.get('location') %}

  📍 {{ item.get('location') }}

  {% endif %}


  ---


  {% elif item_type == 'end' %}


  ### 🏁 {{ journey_date }} · {{ item.get('time_formatted', '—') }}


  📍 **{{ item.get('location', 'Unbekannter Ort') }}**


  {% endif %}


  {% endfor %}


  {% endif %}
