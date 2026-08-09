type: conditional
conditions:
  - condition: numeric_state
    entity: sensor.garage_ford_triplog_route_history
    attribute: route_count
    above: 0
card:
  type: custom:config-template-card
  entities:
    - select.garage_ford_triplog_route_history_date
    - sensor.garage_ford_triplog_route_history
  card:
    type: custom:google-map-card
    api_key: xxx
    zoom: 11
    map_type: terrain
    gesture_handling: greedy
    showScale: true
    keyboardShortcuts: true
    travel_panel_enabled: false
    travel_panel_position: above
    cameraControl: true
    cameraControl_position: RIGHT_BOTTOM
    zoomControl: true
    zoomControl_position: RIGHT_BOTTOM
    streetViewControl: false
    fullscreenControl: true
    fullscreenControl_position: TOP_RIGHT
    mapTypeControl: false
    rotateControl: false
    show_traffic_button: false
    show_weather_button: false
    show_recenter_button: true
    show_recenter_button_position: LEFT_BOTTOM
    show_poi_button: false
    show_datepicker_button: false
    show_daynight_button: false
    buttons_opacity: 1
    marker_clustering: false
    proximity_clustering: false
    spiderfy: true
    show_traffic: true
    weather_layer: none
    geojson_layers:
      - entity: sensor.garage_ford_triplog_route_history
        attribute: geojson
        stroke_color: '#780202'
        stroke_width: 3
        stroke_opacity: 1
        show_popup: true
    zones:
      zone.work:
        show: false
      zone.home:
        show: false
      zone.lidl_schanis:
        show: false
      zone.migros_steinhausen:
        show: false
    entities:
      - entity: sensor.garage_ford_triplog_route_history
        icon_size: 15
        icon_color: '#780202'
        background_color: '#ffffff'
        follow: true
        show_history_dots: false
        show_gps_accuracy: false
        show_gps_accuracy_radius_line: false
        hours_to_show: 0
        use_date_range: false
