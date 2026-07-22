```{=html}
<p align="center">
```
`<img src="https://github.com/weberdomi-ctrl/ford-triplog/raw/main/docs/images/banner.png" alt="Ford Triplog Banner" width="100%">`{=html}
```{=html}
</p>
```
```{=html}
<h1 align="center">
```
Ford Triplog
```{=html}
</h1>
```
```{=html}
<p align="center">
```
`<b>`{=html}Automatic Trip & Energy Logging for Ford vehicles in Home
Assistant`</b>`{=html}
```{=html}
</p>
```
```{=html}
<p align="center">
```
`<img src="https://img.shields.io/badge/Home%20Assistant-2026.6%2B-41BDF5?logo=homeassistant">`{=html}
`<img src="https://img.shields.io/badge/HACS-Default-41BDF5.svg">`{=html}
`<img src="https://img.shields.io/badge/Version-1.3.1-success">`{=html}
`<img src="https://img.shields.io/badge/License-MIT-green">`{=html}
`<img src="https://img.shields.io/badge/Python-3.12+-3776AB?logo=python">`{=html}
```{=html}
</p>
```

------------------------------------------------------------------------

## Why Ford Triplog?

Ford Triplog extends the official FordPass integration by automatically
recording trips and charging sessions and exposing detailed Home
Assistant sensors and statistics.

### Highlights

-   🚗 Automatic trip detection
-   ⚡ Automatic charging detection
-   🔗 Trip ↔ Charge linking
-   📍 Start & destination addresses
-   🔋 Battery and energy statistics
-   📊 Native Home Assistant sensors
-   💾 Local JSON storage
-   🔄 Automatic recovery after restart
-   🚀 Optimized statistics cache
-   🛡 Duplicate trip and charge protection

------------------------------------------------------------------------

# Features

  -----------------------------------------------------------------------
  Trips             Charging          Statistics        Home Assistant
  ----------------- ----------------- ----------------- -----------------
  Automatic trip    Automatic charge  Trip statistics   Config Flow
  detection         detection                           

  Smart Trip        Charge history    Charging          Options Flow
                                      statistics        

  Trip ↔ Charge     Charging duration Average           Native Sensors
  linking                             consumption       

  Start & End       Charge Address    Average distance  Local Storage
  Address                                               

  SOC tracking      Energy added      Totals            Recovery
  -----------------------------------------------------------------------

------------------------------------------------------------------------

# Installation

### Requirements

-   Home Assistant 2026.6+
-   FordPass Integration
-   Supported Ford vehicle

### HACS

1.  Add the repository to HACS.
2.  Restart Home Assistant.
3.  Open **Settings → Devices & Services**.
4.  Add **Ford Triplog**.

------------------------------------------------------------------------

# What's New in 1.3.1

## Added

-   Trip ↔ Charge linking
-   Shared statistics cache
-   Improved recovery logic

## Improved

-   Faster sensor updates
-   Reduced disk access
-   Better coordinator synchronization
-   Improved storage reliability

## Fixed

-   Duplicate trip protection
-   Duplicate charging protection
-   Statistics refresh reliability
-   Various stability improvements

------------------------------------------------------------------------

# Supported Vehicles

✅ Ford Explorer EV

Community tested:

-   Ford Capri EV
-   Mustang Mach-E
-   Puma Gen-E

------------------------------------------------------------------------

# Roadmap

See **ROADMAP.md**.

------------------------------------------------------------------------

# Support

If you enjoy Ford Triplog you can support future development:

**☕ https://ko-fi.com/dompressor**

------------------------------------------------------------------------

# License

MIT License
