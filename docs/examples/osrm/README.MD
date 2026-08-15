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

For larger multi-country datasets (for example Germany + France + Italy
+ Austria + Switzerland + Benelux + Denmark), **32 GB physical RAM should
be considered a minimum for the build machine**, and WSL2/Docker resource
limits may need to be configured explicitly. 24 GB WSL2 memory plus 8 GB
swap is a reasonable starting point on a 32 GB Windows PC.

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

### Windows / Docker Desktop with WSL2

When building larger combined regions with Docker Desktop on Windows, the
default WSL2 resource configuration may be insufficient for `osrm-extract`.

Docker Desktop with the WSL2 backend does not provide a separate memory
slider. Resource limits are managed by Windows through:

``` text
C:\Users\YOUR_USER\.wslconfig
```

For a Windows PC with **32 GB physical RAM**, a suitable starting
configuration for larger multi-country builds is:

``` ini
[wsl2]
memory=24GB
processors=8
swap=8GB
```

After changing `.wslconfig`, restart WSL2 and Docker Desktop:

``` powershell
wsl --shutdown
```

Then start Docker Desktop again.

The exact memory requirement depends on the selected countries and the
OSRM profile. A combined dataset containing Germany, France, Italy and
additional neighbouring countries can require substantially more memory
during `osrm-extract` than the source `.osm.pbf` files themselves suggest.

If Docker terminates `osrm-extract` with:

``` text
docker failed with exit code 137
```

this commonly indicates that the container was killed because of memory
pressure. Check the available WSL2 memory before reducing the dataset or
changing the OSRM configuration.

The WSL2 memory setting applies to the complete WSL2 environment, not only
to the OSRM container. Leave sufficient physical RAM available for Windows
and other applications.


### Destination server

The destination system requires:

-   Docker
-   SSH access
-   SSH key authentication for unattended deployment
-   Permission for the SSH user to execute Docker commands
-   Sufficient storage for the OSRM dataset

When automatic container restart is used on Synology DSM, passwordless
`sudo` access should be configured specifically for the Docker executable.

A Synology NAS, Linux server or similar Docker host can be used.

------------------------------------------------------------------------

# Combined Region Example

The original example builds a combined routing dataset for:

-   Germany
-   Austria
-   Switzerland

The update script can also be configured for larger multi-country
regions. The current extended test setup uses:

-   Germany
-   Austria
-   Switzerland
-   France
-   Italy
-   Netherlands
-   Belgium
-   Denmark
-   Luxembourg

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

## Synology SSH / Docker Permissions

The update script connects to the Synology through SSH after uploading
the finished dataset and restarts the OSRM Docker container.

On Synology DSM, the Docker CLI is typically located at:

``` bash
/usr/local/bin/docker
```

A normal SSH user may be able to log in successfully but still receive:

``` text
permission denied while trying to connect to the Docker daemon socket
```

For unattended deployment, the SSH user can be granted passwordless
`sudo` access specifically to the Docker executable.

As `root`, create a dedicated sudoers file:

``` bash
echo 'YOUR_NAS_USER ALL=(root) NOPASSWD: /usr/local/bin/docker' \
  > /etc/sudoers.d/docker-osrm

chmod 440 /etc/sudoers.d/docker-osrm
```

Replace `YOUR_NAS_USER` with the SSH account used by the update script.

Test the configuration while logged in as that user:

``` bash
sudo /usr/local/bin/docker ps
```

The command must complete without asking for a password.

The PowerShell script can then use:

``` powershell
$RemoteDocker = "sudo /usr/local/bin/docker"
```

Do not store the Synology administrator or root password in the
PowerShell script.

------------------------------------------------------------------------

## Example OSRM Container

The destination server can run the finished dataset with:

``` bash
sudo /usr/local/bin/docker run -d \
  --name OSRM-Triplog \
  --restart unless-stopped \
  --memory=6g \
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

The example limits the running OSRM container to **6 GB RAM**. This is
a practical starting point for the DACH dataset on a shared Docker host.
The required runtime memory depends on the dataset and workload, so the
limit may need to be adjusted for other regions or systems.

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

$RemoteDocker = "sudo /usr/local/bin/docker"

# Reuse downloads/builds up to this age
$MaxFileAgeDays = 2
```

Do not publish your private SSH key or credentials.

------------------------------------------------------------------------

## Reusing Recent Downloads and Builds

The current update script can reuse recently downloaded source files and
an already completed OSRM build.

By default:

``` powershell
$MaxFileAgeDays = 2
```

If the Germany, Austria and Switzerland `.osm.pbf` files are no older
than this limit, they are reused instead of downloaded again.

A completed `dach-latest.osrm*` build is also reused when:

-   at least the expected OSRM output files are present
-   the build is no older than the configured limit
-   the build is newer than the source `.osm.pbf` files

When these conditions are met, the script can continue directly with:

``` text
Local OSRM test
        |
SCP upload
        |
Verify uploaded files
        |
Restart production OSRM
        |
Final NAS test
```

This is especially useful if a deployment or validation step fails after
the time-consuming preprocessing has already completed.

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
