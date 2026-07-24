# Ford Triplog Roadmap

This roadmap outlines the planned evolution of Ford Triplog. Features and priorities may change based on user feedback, Home Assistant developments and FordPass capabilities.

---

# Version 1.0 – Initial Release

- Automatic trip detection
- GPS-based trip recording
- Address lookup
- Odometer-based distance calculation
- State of Charge (SOC) tracking
- Trip history
- Native Home Assistant integration

# Version 1.1 – Smart Trip

- Smart Trip support
- Merge short stops into a single trip
- Configurable Smart Trip timeout
- Improved trip detection
- Better recovery after Home Assistant restart

# Version 1.2 – Statistics

- Energy consumption calculation
- kWh/100 km
- Average speed
- Last trip sensors
- Vehicle statistics
- Improved recovery and stability

# Version 1.3 – Charging Sessions

- Dedicated charging model
- Charge IDs
- Schema versioning
- Extended metadata
- Trip ↔ charging session linking
- Shared history model
- Improved recovery
- Optimized history and cache handling

# Version 1.4 – Smart Charging Sites

- Automatic charging-site recognition
- OpenStreetMap Overpass integration
- Country-specific charging-site databases
- Charging-site database download
- Charging-site database import
- Local geohash index
- Charging station name
- Operator and network
- Charging power
- Connector information
- Charging point count
- Charging-site sensors and attributes
- Complete Home Assistant translations
- Extended documentation

---

# Planned Features

## Version 1.5 – Enhanced Charging Intelligence

### FordPass Integration

- Use the FordPass "Last Charging Session" sensor as the primary source for completed charging sessions
- Import charging start and end SOC
- Import charged energy
- Import charging duration
- Import added driving range
- Import charger type
- Import additional FordPass charging attributes where available

### Charging Site Intelligence

- Use the FordPass charging location as the primary source
- Import station name, network, address and coordinates
- Use the local OpenStreetMap database as a fallback
- Enrich FordPass data with OSM metadata
- Never overwrite valid FordPass data with empty OSM values
- Validate that the FordPass charging record belongs to the current charging session
- Optionally store the source of imported values

### Trip Validation & Data Quality

- Improved trip plausibility validation
- Detect trips with a net SOC increase
- Prevent negative energy consumption values
- Prevent negative consumption (kWh/100 km)
- Exclude invalid consumption values from statistics
- Detect charging events during or immediately before/after a trip
- Distinguish measured values from calculated values
- Additional consistency checks for trip data

### Home Charging

- Configurable home charging location
- Custom home location name (for example "Home")
- Address or coordinate configuration
- Automatic coordinate generation
- Configurable detection radius
- Automatically identify home charging sessions
- Display the custom home location instead of only the postal address

### Charging Analytics

- Improved AC/DC detection
- Better average charging power calculation
- Compare FordPass and Triplog values
- Use calculated values only when FordPass data is unavailable
- Additional sensors and attributes
- General charging improvements

## Version 1.6 – Statistics Center

- Monthly and yearly statistics
- AC/DC charging statistics
- Home vs. public charging
- Average charging power
- Average charging energy
- Most-used charging provider
- Additional Home Assistant sensors
- Dashboard cards
- CSV export
- GPX export

## Version 1.7 – Charging Costs & Maintenance

### Charging Costs

- Manual public charging costs
- Home charging cost calculation
- Configurable electricity tariffs
- Seasonal tariffs
- High/low tariff support
- Cost per charging session
- Cost statistics
- Cost per 100 km

### Maintenance

- Maintenance section in the integration options
- Rebuild all statistics
- Cache verification
- Repair history cache
- Rebuild latest trip and charging snapshots

## Version 1.8 – Long-Term Storage

- Optional SQLite backend
- JSON remains the default storage
- Better performance for large histories
- Advanced filtering
- Extended long-term statistics
- Foundation for future analytics

## Future

- Multi-vehicle support
- Vehicle comparison
- Fleet overview
- Timeline view
- Backup and export tools

---

# Long-Term Vision

Ford Triplog aims to become a complete local EV driving and charging companion for Home Assistant.

The long-term goal is to provide:

- Trip history
- Charging history
- Charging-site intelligence
- Consumption analysis
- Cost tracking
- Statistics
- Unified trip and charging timeline

All data remains local and under the user's control.
