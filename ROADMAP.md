# Ford Triplog 1.8

## 🚀 New Features

### ⚡ Charging Costs

Ford Triplog now supports comprehensive charging cost tracking.

New capabilities include:

- Manual charging cost editor
- Automatic total cost calculation
- Energy costs
- Session fees
- Time-based fees
- Blocking fees
- Parking fees
- Additional costs
- Cost verification flag
- Receipt support
- Currency support

### 🏠 Home Charging Tariffs

Home charging costs can now be calculated automatically.

Features:

- Two configurable seasonal tariffs
- Summer tariff with configurable date range
- Winter tariff with configurable date range
- Automatic tariff selection based on charging date
- Automatic cost calculation for charging sessions inside the configured Home zone

### 🔋 Energy Tracking

Charging sessions now distinguish between:

- Energy stored in the vehicle
- Energy billed by the charging provider
- Charging losses
- Effective charging price
- Energy source tracking

### 🚗 Journey Enhancements

Journeys now include extended energy and charging statistics.

New Journey attributes:

- Charging cost total
- Charging energy cost
- Additional charging cost
- Average charging price
- Battery energy balance
- Total energy flow
- Battery energy delta
- Billed charging energy

### 📊 Dashboard Improvements

The supplied Home Assistant dashboard examples have been extended with:

- Journey charging costs
- Average charging price
- Billed charging energy
- Improved Last Charge dashboard
- Improved Journey dashboard
- Unified charging location display

---

## ✨ Improvements

- Unified charging location display
- Home Assistant zones are preferred over charging site names
- Improved Journey timeline
- Improved Last Charge sensor
- Richer Journey sensor attributes
- Better charging location handling
- Improved cost calculations
- Cleaner dashboard presentation

---

## 🛠 Fixes

- Correct average charging price calculation using billed energy when available
- Improved Journey cost aggregation
- Better handling of manually entered charging costs
- Ignore invalid charging sessions during Journey processing
- Improved handling of unavailable SOC values
- Multiple stability improvements in charging session processing

---

## 🌍 Translations

Updated translations for:

- English
- German
- Polish

including all charging cost related user interface elements.

---

## ❤️ Thank You

Thank you to everyone testing Ford Triplog and providing ideas and feedback.

Your reports and suggestions continue to shape the development of the integration.