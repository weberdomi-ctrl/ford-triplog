type: markdown
content: |2-
    {% set s = 'sensor.garage_ford_triplog_journey_history' %}
    {% set pauses = state_attr(s, 'pause_receipts') or [] %}

    # 🧾 Pausen-Belege

    {% if pauses | count > 0 %}

      {% for pause in pauses %}

    ### ⏸️ {{ pause.get('title') or pause.get('category') or 'Pause' }}

    {% if pause.get('start_time') %}
      {% set dt = as_datetime(pause.get('start_time')) | as_local %}
    📅 **{{ dt.strftime('%d.%m.%Y %H:%M') }}**
    {% endif %}

    ⏱️ **Dauer:** {{ pause.get('duration', '—') }}  
    📍 **Ort:** {{ pause.get('location', 'Unbekannt') }}

    {% if pause.get('cost_total') is not none %}
    💰 **Kosten:** {{ '%.2f' | format(pause.get('cost_total')) }} {{ pause.get('currency', '') }}
    {% endif %}

    {% if pause.get('note') %}
    📝 **Notiz:** {{ pause.get('note') }}
    {% endif %}

    {% set receipts = pause.get('receipts', []) %}

    {% for receipt in receipts %}
    🧾 **{{ receipt.get('note') or ('Beleg ' ~ loop.index) }}**  
    <a href="{{ receipt.get('receipt_url') }}" target="_blank" rel="noopener">
    📄 Beleg öffnen
    </a>
    {% endfor %}

    {% if not loop.last %}
    ---
    {% endif %}

      {% endfor %}

    {% else %}
    Für diesen Tag sind keine Pausen-Belege vorhanden.
    {% endif %}
