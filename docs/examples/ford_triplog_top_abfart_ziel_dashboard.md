🏆 Top-Startorte & Ziele

  {% set departures = state_attr('sensor.garage_ford_triplog', 'top_departures') or [] %}
  {% set destinations = state_attr('sensor.garage_ford_triplog', 'top_destinations') or [] %}

  ### Abfahrten

  {% for item in departures %}
  **{{ loop.index }}. {{ 'Zuhause' if item.location == 'Home' else item.location }}**  
  {{ item.trips }} Fahrten · {{ item.distance_km }} km

  {% endfor %}

  ### Ziele

  {% for item in destinations %}
  **{{ loop.index }}. {{ 'Zuhause' if item.location == 'Home' else item.location }}**  
  {{ item.trips }} Fahrten · {{ item.distance_km }} km

  {% endfor %}