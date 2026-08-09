type: markdown
content: >-
  {% set s = 'sensor.garage_ford_triplog_charging_history' %}

  {% set charges = state_attr(s, 'charges') or [] %}


  {% set history_date_raw = state_attr(s, 'date') %}


  {% if history_date_raw not in [none, '', 'unknown', 'unavailable'] %}
    {% set dt = history_date_raw | as_datetime | as_local %}
    {% set history_date = dt.strftime('%d.%m.%Y') %}
  {% else %}
    {% set history_date = '—' %}
  {% endif %}


  # ⚡ Ford Triplog – Ladehistorie


  ## 📅 {{ history_date }}


  {% if charges | count == 0 %}


  Für diesen Tag sind keine Ladevorgänge vorhanden.


  {% else %}


  ## 📊 Tagesübersicht


  - ⚡ Ladevorgänge: **{{ state_attr(s, 'charge_count') | int(0) }}**

  - ⏱️ Ladezeit: **{{ state_attr(s, 'charging_duration') }}**

  - 🔋 Energie im Fahrzeug: **{{ state_attr(s, 'energy_added_kwh') | float(0) |
  round(2) }} kWh**


  {% if state_attr(s, 'energy_billed_kwh') | float(0) > 0 %}

  - 🧾 Abgerechnete Energie: **{{ state_attr(s, 'energy_billed_kwh') | float(0)
  | round(2) }} kWh**

  {% endif %}


  {% if state_attr(s, 'cost_total') | float(0) > 0 %}

  - 💳 Gesamtkosten: **{{ state_attr(s, 'cost_total') | float(0) | round(2) }}
  {{ state_attr(s, 'currency') or '' }}**

  {% endif %}


  ---


  {% for charge in charges %}


  {% set location = charge.get('location') or 'Unbekannter Ladeort' %}


  {% set start_soc = charge.get('start_soc') %}

  {% set end_soc = charge.get('end_soc') %}


  {% if start_soc is not none and end_soc is not none %}
    {% set soc_added = (end_soc | float(0)) - (start_soc | float(0)) %}
  {% else %}
    {% set soc_added = none %}
  {% endif %}


  {% set energy_added = charge.get('energy_added_kwh') %}

  {% set energy_billed = charge.get('energy_billed_kwh') %}

  {% set energy_source = charge.get('energy_source') %}

  {% set billed_source = charge.get('energy_billed_source') %}


  {% set loss_kwh = charge.get('charging_loss_kwh') %}

  {% set loss_percent = charge.get('charging_loss_percent') %}


  {% set energy_cost = charge.get('energy_cost') %}

  {% set session_fee = charge.get('session_fee') %}

  {% set time_fee = charge.get('time_fee') %}

  {% set blocking_fee = charge.get('blocking_fee') %}

  {% set parking_fee = charge.get('parking_fee') %}

  {% set other_cost = charge.get('other_cost') %}

  {% set total_cost = charge.get('cost_total') %}


  {% set energy_price = charge.get('energy_price_per_kwh') %}

  {% set effective_price = charge.get('effective_price_per_kwh') %}

  {% set currency = charge.get('currency') or '' %}

  {% set cost_source = charge.get('cost_source') %}

  {% set cost_verified = charge.get('cost_verified', false) %}

  {% set receipt = charge.get('receipt_filename') %}


  {% set start_time = charge.get('start_time') %}

  {% set end_time = charge.get('end_time') %}

  {% set duration = charge.get('duration') %}


  {% if start_time %}
    {% set start_dt = as_datetime(start_time) | as_local %}
    {% set charge_date = start_dt.strftime('%d.%m.%Y') %}
    {% set start_clock = start_dt.strftime('%H:%M') %}
  {% else %}
    {% set charge_date = history_date %}
    {% set start_clock = '—' %}
  {% endif %}


  {% if end_time %}
    {% set end_dt = as_datetime(end_time) | as_local %}
    {% set end_clock = end_dt.strftime('%H:%M') %}
  {% else %}
    {% set end_clock = '—' %}
  {% endif %}


  {% set cost_source_text =
    '🏠 Heimtarif' if cost_source == 'home_tariff'
    else '✍️ Manuell erfasst' if cost_source == 'manual'
    else '📄 OCR / Beleg' if cost_source == 'ocr'
    else '🏢 Arbeitstarif' if cost_source == 'work_tariff'
    else cost_source
  %}


  {% set energy_source_text =
    'SOC-berechnet' if energy_source == 'calculated'
    else 'FordPass' if energy_source == 'fordpass'
    else energy_source
  %}


  # ⚡ {{ location }}


  ## {{ charge_date }} · {{ start_clock }}–{{ end_clock }}


  {% if start_soc is not none and end_soc is not none %}

  🔋 **{{ start_soc | round(0) | int }} → {{ end_soc | round(0) | int }} %**

  {% if soc_added is not none %}

  · **+{{ soc_added | round(0) | int }} %**

  {% endif %}

  {% endif %}


  {% if energy_added is not none %}

  ⚡ **{{ energy_added | float(0) | round(2) }} kWh**

  {% endif %}


  {% if total_cost is not none %}

  💳 **{{ total_cost | float(0) | round(2) }} {{ currency }}**

  {% endif %}


  {% if effective_price is not none %}

  📊 **{{ effective_price | float(0) | round(4) }} {{ currency }}/kWh**

  {% endif %}


  ---


  ### 📊 Ladevorgang


  {% if start_soc is not none %}

  - 🔋 Start-SOC: **{{ start_soc | float(0) | round(1) }} %**

  {% endif %}


  {% if end_soc is not none %}

  - 🏁 End-SOC: **{{ end_soc | float(0) | round(1) }} %**

  {% endif %}


  {% if soc_added is not none %}

  - 📈 SOC geladen: **+{{ soc_added | round(1) }} %**

  {% endif %}


  {% if energy_added is not none %}

  - ⚡ Energie im Fahrzeug: **{{ energy_added | float(0) | round(2) }} kWh**

  {% endif %}


  {% if energy_billed is not none %}

  - 🧾 Abgerechnete Energie: **{{ energy_billed | float(0) | round(2) }} kWh**

  {% endif %}


  {% if loss_kwh is not none and loss_kwh | float(0) > 0 %}

  - ♻️ Ladeverlust: **{{ loss_kwh | float(0) | round(2) }} kWh**

  {% if loss_percent is not none %}
    (**{{ loss_percent | float(0) | round(1) }} %**)
  {% endif %}

  {% endif %}


  {% if duration %}

  - ⏱️ Ladedauer: **{{ duration }}**

  {% endif %}


  {% if energy_source %}

  - 🗂️ Energiequelle: **{{ energy_source_text }}**

  {% endif %}


  {% if billed_source and billed_source != 'none' %}

  - 🧾 Abrechnungsquelle: **{{ billed_source }}**

  {% endif %}


  {% if total_cost is not none %}


  ### 💰 Ladekosten


  {% if energy_cost is not none %}

  - ⚡ Energiekosten: **{{ energy_cost | float(0) | round(2) }} {{ currency }}**

  {% endif %}


  {% if session_fee is not none and session_fee | float(0) > 0 %}

  - ▶️ Sessiongebühr: **{{ session_fee | float(0) | round(2) }} {{ currency }}**

  {% endif %}


  {% if time_fee is not none and time_fee | float(0) > 0 %}

  - ⏱️ Zeitgebühr: **{{ time_fee | float(0) | round(2) }} {{ currency }}**

  {% endif %}


  {% if blocking_fee is not none and blocking_fee | float(0) > 0 %}

  - 🚧 Blockiergebühr: **{{ blocking_fee | float(0) | round(2) }} {{ currency
  }}**

  {% endif %}


  {% if parking_fee is not none and parking_fee | float(0) > 0 %}

  - 🅿️ Parkgebühr: **{{ parking_fee | float(0) | round(2) }} {{ currency }}**

  {% endif %}


  {% if other_cost is not none and other_cost | float(0) > 0 %}

  - ➕ Sonstige Kosten: **{{ other_cost | float(0) | round(2) }} {{ currency }}**

  {% endif %}


  - 💳 Gesamtkosten: **{{ total_cost | float(0) | round(2) }} {{ currency }}**


  {% if energy_price is not none %}

  - ⚡ Energiepreis: **{{ energy_price | float(0) | round(4) }} {{ currency
  }}/kWh**

  {% endif %}


  {% if effective_price is not none %}

  - 📊 Effektiver Preis: **{{ effective_price | float(0) | round(4) }} {{
  currency }}/kWh**

  {% endif %}


  {% if cost_source %}

  - {{ cost_source_text }}

  {% endif %}


  {% if cost_verified %}

  - ✅ Kosten bestätigt

  {% endif %}


  {% endif %}


  ### 📍 Ladeort


  **{{ location }}**


  {% if charge.get('start_latitude') is not none
        and charge.get('start_longitude') is not none %}

  Koordinaten:  

  {{ charge.get('start_latitude') }}, {{ charge.get('start_longitude') }}


  [Auf Karte anzeigen](https://www.openstreetmap.org/?mlat={{
  charge.get('start_latitude') }}&mlon={{ charge.get('start_longitude')
  }}#map=17/{{ charge.get('start_latitude') }}/{{ charge.get('start_longitude')
  }})


  {% endif %}


  {% if receipt %}


  ### 🧾 Beleg


  Beleg vorhanden: **{{ receipt }}**


  {% endif %}


  {% if not loop.last %}

  ---

  {% endif %}


  {% endfor %}


  {% endif %}
