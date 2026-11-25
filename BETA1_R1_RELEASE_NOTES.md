# Ford Triplog 2.8.0 Beta 1 R1

Version: `2.8.0-beta.1-r1`
Build: `28001`
Test branch: `2.8.0-beta.1-r1`

## What's new

- Home Assistant administrators get a **Triplog** sidebar panel at
  `/ford-triplog-logbook`. Select a vehicle and date to browse archived drives,
  charges and stops.
- Edit the location, note or cost of an archived charge, or add a completed
  charge with billed energy. Add details and costs to detected journey stops.
- The optional [Lovelace statistics template](docs/examples/ford_triplog_statistics_dashboard.yaml)
  uses the full German statistics layout. Replace the example entity IDs
  with those from your installation before saving the dashboard.

## Verify the installed build

After installing this branch and restarting Home Assistant, check that the
integration reports `2.8.0-beta.1-r1`. At INFO log level, the startup message
reads `Ford Triplog 2.8.0-beta.1-r1 (build 28001) initialized`.
Open **Triplog** from the sidebar with an administrator account.

This is a test build. Manual stops with custom start and end times are not
included in this build.
