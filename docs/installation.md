# Installation

Ford Triplog is designed to integrate seamlessly with Home Assistant and the official FordPass integration.

This guide explains both the recommended HACS installation and the manual installation process.

---

# Requirements

Before installing Ford Triplog, ensure the following requirements are met.

| Requirement | Status |
| :---------- | :----: |
| Home Assistant 2026.6 or newer | ✅ Required |
| HACS | ✅ Recommended |
| FordPass Integration | ✅ Required |
| Supported Ford EV | ✅ Required |

> [!IMPORTANT]
> Ford Triplog extends the FordPass integration.
>
> It does **not** replace FordPass.
>
> Install and configure the FordPass integration before adding Ford Triplog.

---

# Install using HACS (Recommended)

Installing through HACS ensures you always receive future updates easily.

## Step 1

Open **HACS**

↓

**Integrations**

↓

Search for

```
Ford Triplog
```

---

## Step 2

Select

```
Download
```

---

## Step 3

Restart Home Assistant.

---

## Step 4

Open

```
Settings

↓

Devices & Services
```

Click

```
Add Integration
```

and select

```
Ford Triplog
```

---

# Manual Installation

If you prefer not to use HACS, Ford Triplog can also be installed manually.

Download the latest release from GitHub.

Copy

```
custom_components/ford_triplog
```

to

```
config/custom_components/
```

The resulting directory structure should look like:

```
config/

└── custom_components/

    └── ford_triplog/

        __init__.py
        manifest.json
        config_flow.py
        coordinator.py
        sensor.py
        ...
```

Restart Home Assistant.

Open

```
Settings

↓

Devices & Services

↓

Add Integration
```

Select

```
Ford Triplog
```

---

# Updating

## HACS

Updates are handled automatically through HACS.

Simply install the available update and restart Home Assistant.

---

## Manual Installation

Replace the

```
custom_components/ford_triplog
```

directory with the new release files.

Restart Home Assistant afterwards.

---

# Uninstalling

Removing Ford Triplog does **not** automatically delete your stored trip history.

To completely remove all data:

1. Remove the integration.
2. Delete

```
custom_components/ford_triplog
```

3. Delete

```
/config/.storage/ford_triplog/
```

> [!WARNING]
> Deleting the storage folder permanently removes:
>
> - Trip history
> - Charging history
> - Statistics
> - Recovery data

---


---

# Optional Charging-Site Database

After the initial configuration you can optionally download a local charging-site database from the integration options.

This enables Ford Triplog to recognize public charging stations and enrich charging sessions with:

- Station name
- Brand
- Operator
- Charging network
- Connector information
- Charging power

The download is only required once per country and can be refreshed at any time.


# Next Step

After the installation has finished, continue with the configuration guide.

➡ **[Configuration](configuration.md)**