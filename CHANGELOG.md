# Changelog

## 1.2.3



### Fixed



\- Fixed timezone handling for trip and charging timestamps.

\- All timestamps now use Home Assistant's timezone-aware datetime handling.

\- Improved consistency of trip and charge data.

\- Fixed incorrect UTC display for "Last Charge" timestamps.



### New

#### Charging

* Added complete charging session recording
* Automatic charging start detection
* Automatic charging end detection
* Charging recovery after Home Assistant restart
* Local charging history
* Last charging cache

#### Charging Sensors

* Last Charge Time
* Last Charge End Time
* Last Charge Duration
* Last Charge Address
* Last Charge Start SOC
* Last Charge End SOC
* Last Charge SOC Added

#### Trip Sensors

* Last Trip Start SOC
* Last Trip End SOC
* Last Trip SOC Used

#### Statistics

Added charging statistics:

* Charge Count
* Average Charge Duration
* Average Charge Start SOC
* Average Charge End SOC
* Average Charge SOC Added

Added trip statistics:

* Average Trip Distance
* Average Trip Duration
* Average Trip Energy Used
* Average Trip Consumption
* Average Trip SOC Used

### Changed

* Improved history handling
* Improved statistics engine
* Improved recovery handling
* Improved local storage
* Cleaner sensor naming
* Improved address formatting

### Fixed

* Various recovery issues
* Storage consistency improvements
* Sensor update improvements
* Statistics calculation improvements

## Version 1.2.0 beta

### Added

* New sensors:
* Last Trip Start Time
* Last Trip End Time
* Last Trip Date
* Average Trip Distance
* Average Trip Duration
* Longest Trip
* Shortest Trip
* Human-readable trip timestamps ("Heute", "Gestern", Datum/Uhrzeit).

### Changed

* Improved local time handling using Home Assistant's timezone utilities.
* Trip timestamps are now correctly converted from UTC to the configured Home Assistant timezone.
* Internal date/time formatting moved to a shared utility function.

### Fixed

* Fixed incorrect UTC display for trip start and end times.
* Improved consistency of date and time formatting across all trip sensors.

## 1.1.0

### Added

* Config Flow
* Options Flow
* Smart Trip
* Smart Trip timeout
* Home Assistant Brands Proxy API
* German and English translations

### Improved

* Modernized integration architecture
* Automatic reload after option changes
* Improved configuration handling

### Fixed

* Config Flow issues
* Options handling
* Home Assistant 2026.6 compatibility

