# Local OSRM Routing for Ford Triplog

Ford Triplog can optionally use a local
[OSRM](https://project-osrm.org/) server to improve recorded GPS tracks
by matching them to the road network.

Running OSRM locally avoids dependency on public routing services and
allows route processing entirely inside your own network.

This directory contains example scripts and instructions for building
and maintaining an OSRM dataset.

> OSRM is optional. Ford Triplog works without a local OSRM server.

------------------------------------------------------------------------

## Recommended Architecture

For larger map regions, it is recommended to separate OSRM preprocessing
from the system running Home Assistant.

Example:

``` text
Geofabrik OSM data
        |
        v
Windows PC / Build machine
        |
        |  Download
        |  Merge
        |  osrm-extract
        |  osrm-partition
        |  osrm-customize
        |
        v
Finished OSRM dataset
        |
        |  SCP / SFTP
        v
NAS / Docker host
        |
        v
OSRM routing server
        |
        v
Ford Triplog
```

The preprocessing steps require considerably more CPU and memory than
the running OSRM routing service.

------------------------------------------------------------------------

## Hardware Requirements

Actual requirements depend on the size and complexity of the selected
OpenStreetMap dataset.

### Small country datasets

Smaller datasets, such as Switzerland, can usually be prepared on
systems with relatively limited resources.

### Larger datasets

For larger countries or combined regions, preprocessing should
preferably be performed on a PC or server.

For the combined Germany + Austria + Switzerland (**DACH**) dataset:

-   SSD or NVMe storage recommended
-   16 GB RAM may be insufficient
-   **32 GB RAM recommended**
-   Multi-core CPU recommended

During testing, preprocessing of the DACH dataset exceeded the available
memory of a Docker host with 10 GB RAM.

`osrm-partition` alone reached approximately **12 GB peak memory
usage**.

The finished routing dataset requires significantly fewer resources to
operate than the preprocessing stage.

Therefore, a small NAS can still be suitable for running OSRM even when
it cannot build the dataset itself.

------------------------------------------------------------------------

## Requirements

### Build machine

The provided PowerShell example requires:

-   Windows 10 or Windows 11
-   Docker Desktop
-   Linux containers / WSL2
-   PowerShell
-   PuTTY tools
    -   `pscp.exe`
    -   `plink.exe`
-   SSH access to the destination Docker host
-   Sufficient free disk space

For DACH, at least **30--40 GB of temporary free disk space** is
recommended.

### Destination server

The destination system requires:

-   Docker
-   SSH access
-   Sufficient storage for the OSRM dataset

A Synology NAS, Linux server or similar Docker host can be used.

------------------------------------------------------------------------

# DACH Example

The included PowerShell script builds a combined routing dataset for:

-   Germany
-   Austria
-   Switzerland

OpenStreetMap data is downloaded from Geofabrik.

The resulting dataset allows routing across country borders.

For example:

``` text
Switzerland -> Austria
Switzerland -> Germany
Germany -> Austria
```

------------------------------------------------------------------------

## Directory

The example uses:

``` text
C:\osrm
```

as the local working directory.

The script downloads:

``` text
germany-latest.osm.pbf
austria-latest.osm.pbf
switzerland-latest.osm.pbf
```

and creates:

``` text
dach-latest.osm.pbf
```

The final OSRM files use the prefix:

``` text
dach-latest.osrm
```

------------------------------------------------------------------------

# OSRM Build Process

The update process consists of the following stages.

## 1. Download OpenStreetMap data

Current `.osm.pbf` files are downloaded from Geofabrik.

## 2. Merge countries

Germany, Austria and Switzerland are merged into one DACH dataset.

``` text
Germany
   +
Austria
   +
Switzerland
   |
   v
dach-latest.osm.pbf
```

## 3. Extract

OSRM converts the OpenStreetMap data using the standard car profile:

``` bash
osrm-extract -p /opt/car.lua /data/dach-latest.osm.pbf
```

This is usually the most memory-intensive step.

## 4. Partition

The dataset is prepared for the OSRM MLD algorithm:

``` bash
osrm-partition /data/dach-latest.osrm
```

## 5. Customize

The final routing graph is generated:

``` bash
osrm-customize /data/dach-latest.osrm
```

## 6. Local validation

Before anything is uploaded to the production server, the script starts
a temporary local OSRM container.

Routing is tested in:

-   Switzerland
-   Germany
-   Austria

A cross-border route is also tested.

Only after these tests succeed does the deployment continue.

------------------------------------------------------------------------

# Deploying to the Docker Host

The finished files are transferred using SCP.

Example:

``` powershell
pscp.exe -i C:\Users\YOUR_USER\.ssh\synology.ppk `
    C:\osrm\dach-latest.osrm* `
    YOUR_USER@192.168.1.100:/volume1/docker/osrm/
```

SSH key authentication is strongly recommended.

Do not store SSH passwords inside the PowerShell script.

------------------------------------------------------------------------

## Example OSRM Container

The destination server can run the finished dataset with:

``` bash
docker run -d \
  --name OSRM-Triplog \
  --restart unless-stopped \
  -p 5005:5000 \
  -v /volume1/docker/osrm:/data \
  osrm/osrm-backend:latest \
  osrm-routed --algorithm mld /data/dach-latest.osrm
```

This example exposes OSRM on:

``` text
http://SERVER-IP:5005
```

The paths and ports can be changed to match your environment.

------------------------------------------------------------------------

# PowerShell Update Script

The example `Update-OSRMDACH.ps1` can automate the complete process:

``` text
Download
   |
Merge
   |
Extract
   |
Partition
   |
Customize
   |
Local routing tests
   |
SCP upload
   |
Verify uploaded files
   |
Restart OSRM
   |
Final routing tests
```

Before using the script, edit the configuration section.

Example:

``` powershell
$WorkDir = "C:\osrm"

$SshKey = "C:\Users\YOUR_USER\.ssh\synology.ppk"

$NasUser = "YOUR_NAS_USER"
$NasHost = "192.168.1.100"

$NasTarget = "/volume1/docker/osrm"
$NasContainer = "OSRM-Triplog"
$NasPort = 5005
```

Do not publish your private SSH key or credentials.

------------------------------------------------------------------------

## Running the Script

If PowerShell script execution is restricted, the script can be started
with:

``` powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\osrm\Update-OSRMDACH.ps1"
```

This does not permanently change the system-wide PowerShell execution
policy.

An optional `.cmd` launcher can also be used:

``` bat
@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-OSRMDACH.ps1"
pause
```

------------------------------------------------------------------------

# Updating the Map Data

OpenStreetMap data changes continuously.

The update script can simply be run again whenever a new routing dataset
is required.

The recommended update workflow is:

``` text
Keep existing OSRM running
        |
Build new dataset externally
        |
Test new dataset locally
        |
Upload completed dataset
        |
Restart OSRM container
        |
Test production OSRM
```

This prevents a failed preprocessing operation from unnecessarily
interrupting the active routing service.

For most Ford Triplog installations, frequent map updates are not
necessary.

A manual update every few weeks or months is usually sufficient.

------------------------------------------------------------------------

# Other Countries

The same concept can be used for other Geofabrik regions.

Examples include:

-   France
-   Italy
-   Poland
-   United Kingdom
-   Ireland

Change the download URLs and merge configuration according to the
required region.

Memory and storage requirements depend heavily on the size of the
selected OpenStreetMap extracts.

Large countries or multi-country datasets should be prepared on a
sufficiently powerful PC or server rather than directly on a small Home
Assistant or NAS system.

------------------------------------------------------------------------

# Public OSRM Servers

Public OSRM services should not be considered a guaranteed backend for
permanent automated Ford Triplog processing.

Public instances may have:

-   usage limits
-   rate limits
-   availability restrictions
-   fair-use policies

For regular route reconstruction, a local OSRM instance is recommended.

------------------------------------------------------------------------

# Ford Triplog Configuration

After OSRM is running, configure Ford Triplog to use the local OSRM
endpoint.

Example:

``` text
http://192.168.1.100:5005
```

The exact address depends on your Docker host and network configuration.

OSRM route matching remains optional and can be enabled or disabled in
the Ford Triplog settings.

------------------------------------------------------------------------

# Notes

OSRM preprocessing can temporarily consume substantial CPU, RAM and disk
I/O.

On systems also running Home Assistant or other services, this may
noticeably reduce system performance.

For this reason, building large datasets externally and copying only the
finished OSRM files to the production Docker host is the recommended
approach.
