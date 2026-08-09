type: markdown
content: |-
  {% set s = 'sensor.garage_ford_triplog_charging_history' %}
  {% set charges = state_attr(s, 'charges') or [] %}

  # 🧾 Belege

  {% set ns = namespace(count=0) %}

  {% for charge in charges %}
    {% set receipts = charge.get('receipts', []) %}

    {% for receipt in receipts %}
      {% set ns.count = ns.count + 1 %}

  ### ⚡ {{ charge.get('location', 'Unbekannter Ladeort') }}

  {% if charge.get('start_time') %}
    {% set dt = as_datetime(charge.get('start_time')) | as_local %}
  📅 {{ dt.strftime('%d.%m.%Y %H:%M') }}
  {% endif %}

  🧾 **{{ receipt.get('filename', 'Beleg') }}**

  [📄 Beleg öffnen]({{ receipt.get('receipt_url') }})

  {% if not loop.last %}
  ---
  {% endif %}

    {% endfor %}
  {% endfor %}

  {% if ns.count == 0 %}
  Für diesen Tag sind keine Belege vorhanden.
  {% endif %}
