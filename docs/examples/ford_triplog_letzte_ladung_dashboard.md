{% set s = 'sensor.garage_ford_triplog_letzter_ladevorgang' %}

# 🚗 Ford Triplog – Letzte Ladung

{% set location =
    state_attr(s, 'display_location')
    or state_attr(s, 'zone_name')
    or state_attr(s, 'charging_location')
    or state_attr(s, 'address')
    or 'Unbekannter Ladeort'
%}

{% set address = state_attr(s, 'address') %}
{% set latitude = state_attr(s, 'latitude') %}
{% set longitude = state_attr(s, 'longitude') %}

{% set start_soc = state_attr(s, 'start_soc') %}
{% set end_soc = state_attr(s, 'end_soc') %}
{% set soc_added = state_attr(s, 'soc_added') %}

{% set energy_added = state_attr(s, 'energy_added_kwh') %}
{% set energy_billed = state_attr(s, 'energy_billed_kwh') %}
{% set energy_source = state_attr(s, 'energy_source') %}
{% set billed_source = state_attr(s, 'energy_billed_source') %}

{% set loss_kwh = state_attr(s, 'charging_loss_kwh') %}
{% set loss_percent = state_attr(s, 'charging_loss_percent') %}

{% set energy_cost = state_attr(s, 'energy_cost') %}
{% set session_fee = state_attr(s, 'session_fee') %}
{% set time_fee = state_attr(s, 'time_fee') %}
{% set blocking_fee = state_attr(s, 'blocking_fee') %}
{% set parking_fee = state_attr(s, 'parking_fee') %}
{% set other_cost = state_attr(s, 'other_cost') %}
{% set total_cost = state_attr(s, 'cost_total') %}

{% set energy_price = state_attr(s, 'energy_price_per_kwh') %}
{% set effective_price = state_attr(s, 'effective_price_per_kwh') %}
{% set currency = state_attr(s, 'currency') or '' %}
{% set cost_source = state_attr(s, 'cost_source') %}
{% set cost_verified = state_attr(s, 'cost_verified') %}

{% set start_time = state_attr(s, 'start_time') %}
{% set end_time = state_attr(s, 'end_time') %}
{% set duration = state_attr(s, 'duration') %}

{% set cost_source_text =
    '🏠 Heimtarif' if cost_source == 'home_tariff'
    else '✍️ Manuell erfasst' if cost_source == 'manual'
    else '📄 OCR  Beleg' if cost_source == 'ocr'
    else '🏢 Arbeitstarif' if cost_source == 'work_tariff'
    else cost_source
%}

{% set energy_source_text =
    'SOC-berechnet' if energy_source == 'calculated'
    else 'FordPass' if energy_source == 'fordpass'
    else energy_source
%}

# ⚡ {{ location }}

{% if start_soc is not none and end_soc is not none %}
🔋 {{ start_soc  round(0)  int }} → {{ end_soc  round(0)  int }} %
{% if soc_added is not none %}
· +{{ soc_added  round(0)  int }} %
{% endif %}
{% endif %}

{% if energy_added is not none %}
⚡ {{ energy_added  round(2) }} kWh
{% endif %}

{% if total_cost is not none %}
💳 {{ total_cost  round(2) }} {{ currency }}
{% endif %}

{% if effective_price is not none %}
📊 {{ effective_price  round(4) }} {{ currency }}kWh
{% endif %}

---

## 📊 Ladevorgang

{% if start_soc is not none %}
- 🔋 Start-SOC {{ start_soc  round(1) }} %
{% endif %}

{% if end_soc is not none %}
- 🏁 End-SOC {{ end_soc  round(1) }} %
{% endif %}

{% if soc_added is not none %}
- 📈 SOC geladen +{{ soc_added  round(1) }} %
{% endif %}

{% if energy_added is not none %}
- ⚡ Energie im Fahrzeug {{ energy_added  round(2) }} kWh
{% endif %}

{% if energy_billed is not none %}
- 🧾 Abgerechnete Energie {{ energy_billed  round(2) }} kWh
{% endif %}

{% if loss_kwh is not none and loss_kwh  0 %}
- ♻️ Ladeverlust {{ loss_kwh  round(2) }} kWh
  {% if loss_percent is not none %}
  ({{ loss_percent  round(1) }} %)
  {% endif %}
{% endif %}

{% if duration %}
- ⏱️ Ladedauer {{ duration }}
{% endif %}

{% if energy_source %}
- 🗂️ Energiequelle {{ energy_source_text }}
{% endif %}

{% if billed_source and billed_source != 'none' %}
- 🧾 Abrechnungsquelle {{ billed_source }}
{% endif %}

{% if total_cost is not none %}

---

## 💰 Ladekosten

{% if energy_cost is not none %}
- ⚡ Energiekosten {{ energy_cost  round(2) }} {{ currency }}
{% endif %}

{% if session_fee is not none and session_fee  0 %}
- ▶️ Sessiongebühr {{ session_fee  round(2) }} {{ currency }}
{% endif %}

{% if time_fee is not none and time_fee  0 %}
- ⏱️ Zeitgebühr {{ time_fee  round(2) }} {{ currency }}
{% endif %}

{% if blocking_fee is not none and blocking_fee  0 %}
- 🚧 Blockiergebühr {{ blocking_fee  round(2) }} {{ currency }}
{% endif %}

{% if parking_fee is not none and parking_fee  0 %}
- 🅿️ Parkgebühr {{ parking_fee  round(2) }} {{ currency }}
{% endif %}

{% if other_cost is not none and other_cost  0 %}
- ➕ Sonstige Kosten {{ other_cost  round(2) }} {{ currency }}
{% endif %}

- 💳 Gesamtkosten {{ total_cost  round(2) }} {{ currency }}

{% if energy_price is not none %}
- ⚡ Energiepreis {{ energy_price  round(4) }} {{ currency }}kWh
{% endif %}

{% if effective_price is not none %}
- 📊 Effektiver Preis {{ effective_price  round(4) }} {{ currency }}kWh
{% endif %}

{% if cost_source %}
- {{ cost_source_text }}
{% endif %}

{% if cost_verified %}
- ✅ Kosten bestätigt
{% endif %}

{% endif %}

---

## 📍 Ladeort

{{ location }}

{% if address and address != location %}
{{ address }}
{% endif %}

{% if latitude is not none and longitude is not none %}

Koordinaten  
{{ latitude }}, {{ longitude }}

[Auf Karte anzeigen](httpswww.openstreetmap.orgmlat={{ latitude }}&mlon={{ longitude }}#map=17{{ latitude }}{{ longitude }})

{% endif %}

---

## 🕒 Ladezeiten

{% if start_time %}
Ladebeginn  
{{ (as_datetime(start_time)  as_local).strftime('%d.%m.%Y %H%M') }}
{% endif %}

{% if end_time %}

Ladeende  
{{ (as_datetime(end_time)  as_local).strftime('%d.%m.%Y %H%M') }}
{% endif %}

{% if duration %}

Dauer  
{{ duration }}
{% endif %}

---

smallDatenquelle Ford Triplogsmall