# Ford Triplog v1.4.0

## 🚗 Major Release

Version 1.4 is the biggest update since the initial release of Ford
Triplog and introduces charging session tracking, OpenStreetMap
integration, improved statistics, and many usability improvements.

## ✨ New Features

### 🔋 Charging Sessions

-   Automatic charging session detection
-   Charging duration
-   Start and end state of charge (SOC)
-   Estimated charged energy
-   Charging history
-   Charging statistics

### 🗺️ Charging Location Database

-   Offline charging location database based on OpenStreetMap
-   Automatic charging location recognition
-   Country-specific charging databases
-   Download charging databases directly from the integration
-   Fast geohash-based lookup
-   Support for multiple European countries

### 🔗 Trip & Charging Timeline

-   Automatic linking of charging sessions with nearby trips
-   Unified travel history
-   Charging events associated with trips

### 📊 Statistics

-   Extended trip statistics
-   Charging statistics
-   Average energy consumption
-   Additional Home Assistant sensors

## ⚙️ Improvements

-   Configurable battery capacity
-   Improved Smart Trip handling
-   Improved entity naming
-   Complete Home Assistant translations
-   Improved diagnostics
-   Faster startup
-   Better error handling
-   Performance optimizations

## 🏗️ Internal

-   HACS ready
-   Improved storage handling
-   Optimized charging database format
-   Faster location lookup
-   General refactoring and cleanup

## 🐞 Fixes

-   Fixed charging database activation
-   Fixed charging database persistence after restart
-   Fixed country selection workflow
-   Fixed configuration flow issues
-   Multiple stability improvements

------------------------------------------------------------------------

Thank you to everyone testing Ford Triplog and providing feedback.
