# Local OSRM Routing for Ford Triplog

Ford Triplog can optionally use a local [OSRM](https://project-osrm.org/) server to improve recorded GPS tracks by matching them to the road network.

Running OSRM locally avoids dependency on public routing services and allows route processing entirely inside your own network.

This directory contains example scripts and instructions for building and maintaining an OSRM dataset.

> OSRM is optional. Ford Triplog works without a local OSRM server.

---

## Recommended Architecture

For larger map regions, it is recommended to separate OSRM preprocessing from the system running Home Assistant.

Example:

```text
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