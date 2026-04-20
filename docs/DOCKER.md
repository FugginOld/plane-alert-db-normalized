# Docker + systemd Deployment Guide

This guide covers building the Docker image, running the pipeline in a container,
and configuring a **systemd timer** so the weekly update runs automatically on boot
and on the weekly schedule (every Sunday at 03:15 local time).

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Build the image](#build-the-image)
- [Run the weekly update once (manual)](#run-the-weekly-update-once-manual)
- [Open an interactive shell inside the container](#open-an-interactive-shell-inside-the-container)
- [Configure the systemd service and timer](#configure-the-systemd-service-and-timer)
  - [Install the units](#install-the-units)
  - [Enable and start the timer](#enable-and-start-the-timer)
  - [Run the service immediately](#run-the-service-immediately)
- [Read logs](#read-logs)
  - [journald (systemd journal)](#journald-systemd-journal)
  - [Persistent log file](#persistent-log-file)
- [Verify the timer schedule](#verify-the-timer-schedule)
- [Stop or disable the timer](#stop-or-disable-the-timer)
- [Directory layout inside the container](#directory-layout-inside-the-container)

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker ≥ 20.10 | Or compatible container runtime. |
| systemd | Standard on most modern Linux distributions. |
| Cloned repository | `git clone https://github.com/FugginOld/aircraft-taxonomy-db.git` |

All commands below assume you have cloned the repository to
`/opt/aircraft-taxonomy-db` (adjust the path to match your environment).

---

## Build the image

Run from the **repository root**:

```bash
cd /opt/aircraft-taxonomy-db
docker build -t plane-alert-db:latest .
```

This creates an image named `plane-alert-db:latest` with Python 3.10, all pip
dependencies pre-installed, and a snapshot of the repository baked in.  At
runtime the volatile directories (`data/`, `taxonomy/`, `cache/`, `build/`,
`logs/`) are bind-mounted from the host, so any changes made inside the container
are persisted automatically.

---

## Run the weekly update once (manual)

Replace `/opt/aircraft-taxonomy-db` with your actual repo path:

```bash
docker run --rm \
    -v /opt/aircraft-taxonomy-db/data:/workspace/data \
    -v /opt/aircraft-taxonomy-db/taxonomy:/workspace/taxonomy \
    -v /opt/aircraft-taxonomy-db/cache:/workspace/cache \
    -v /opt/aircraft-taxonomy-db/build:/workspace/build \
    -v /opt/aircraft-taxonomy-db/logs:/workspace/logs \
    plane-alert-db:latest \
    /workspace/docker/weekly_update.sh
```

Output is written to both the terminal and
`/opt/aircraft-taxonomy-db/logs/weekly_aircraft_update.log`.

---

## Open an interactive shell inside the container

```bash
docker run --rm -it \
    -v /opt/aircraft-taxonomy-db/data:/workspace/data \
    -v /opt/aircraft-taxonomy-db/taxonomy:/workspace/taxonomy \
    -v /opt/aircraft-taxonomy-db/cache:/workspace/cache \
    -v /opt/aircraft-taxonomy-db/build:/workspace/build \
    -v /opt/aircraft-taxonomy-db/logs:/workspace/logs \
    plane-alert-db:latest \
    /bin/bash
```

Inside the shell, `/workspace` is the working directory, so scripts are available
under `/workspace` and can be run using relative paths. For example:

```bash
python scripts/validate_schema.py \
    --lookup taxonomy/aircraft_type_lookup.csv \
    --aliases taxonomy/aircraft_type_aliases.csv \
    --data-files data/plane-alert-db.csv data/plane-alert-pia.csv
```

---

## Configure the systemd service and timer

### Install the units

1. **Copy the example environment file** and set the repository path:

   ```bash
   sudo cp systemd/plane-alert-weekly.env.example /etc/plane-alert-weekly.env
   sudo nano /etc/plane-alert-weekly.env
   # Set REPO_DIR to your actual repository path, e.g.:
   # REPO_DIR=/opt/aircraft-taxonomy-db
   ```

2. **Copy the unit files** to the systemd system directory:

   ```bash
   sudo cp systemd/plane-alert-weekly.service /etc/systemd/system/
   sudo cp systemd/plane-alert-weekly.timer   /etc/systemd/system/
   ```

3. **Reload the systemd daemon**:

   ```bash
   sudo systemctl daemon-reload
   ```

### Enable and start the timer

```bash
# Enable the timer so it survives reboots.
sudo systemctl enable plane-alert-weekly.timer

# Start the timer immediately (without waiting for a reboot).
sudo systemctl start plane-alert-weekly.timer
```

The timer is configured with `Persistent=true`, which means that if the host
was offline when the weekly trigger was due, the service will run on the next
boot instead of being skipped.

### Run the service immediately

To trigger a one-off run without waiting for the next scheduled time:

```bash
sudo systemctl start plane-alert-weekly.service
```

---

## Read logs

### journald (systemd journal)

All output from the container (stdout + stderr) is captured by journald under
the identifier `plane-alert-weekly`.

```bash
# Show the last 200 lines of the most recent run:
journalctl -u plane-alert-weekly.service -n 200

# Follow output in real time while the service is running:
journalctl -u plane-alert-weekly.service -f

# Show all historical entries:
journalctl -u plane-alert-weekly.service --no-pager
```

### Persistent log file

Each run also appends a timestamped record to the log file on the host:

```
/opt/aircraft-taxonomy-db/logs/weekly_aircraft_update.log
```

```bash
tail -n 100 /opt/aircraft-taxonomy-db/logs/weekly_aircraft_update.log
```

---

## Verify the timer schedule

```bash
# Show the timer status, including the last trigger and next scheduled time:
systemctl status plane-alert-weekly.timer

# List all active timers sorted by next trigger time:
systemctl list-timers --all | grep plane-alert
```

Example output:

```
NEXT                         LEFT          LAST                         PASSED   UNIT                          ACTIVATES
Sun 2026-04-26 03:15:00 BST  5 days left   Sun 2026-04-19 03:15:00 BST  6 days ago  plane-alert-weekly.timer  plane-alert-weekly.service
```

---

## Stop or disable the timer

```bash
# Stop the timer for this boot only (re-enables on reboot):
sudo systemctl stop plane-alert-weekly.timer

# Permanently disable the timer:
sudo systemctl disable plane-alert-weekly.timer
sudo systemctl stop plane-alert-weekly.timer
```

---

## Directory layout inside the container

| Container path | Source | Persisted? |
|---|---|---|
| `/workspace/scripts/` | Baked into image | — |
| `/workspace/docker/` | Baked into image | — |
| `/workspace/data/` | Host bind mount | ✅ Yes |
| `/workspace/taxonomy/` | Host bind mount | ✅ Yes |
| `/workspace/cache/public_sources/` | Host bind mount | ✅ Yes |
| `/workspace/build/weekly_update/` | Host bind mount | ✅ Yes |
| `/workspace/logs/` | Host bind mount | ✅ Yes |

After each weekly run the following files are updated on the host:

| File | Description |
|---|---|
| `taxonomy/aircraft_type_lookup.csv` | Updated canonical ICAO type lookup |
| `taxonomy/aircraft_type_aliases.csv` | Updated canonical aliases |
| `data/plane-alert-db.csv` | Re-normalised main aircraft database |
| `data/plane-alert-pia.csv` | Re-normalised PIA database |
| `data/plane-alert-wip.csv` | Re-normalised WIP database |
| `build/weekly_update/weekly_update_manifest.json` | JSON summary of the run |
| `logs/weekly_aircraft_update.log` | Appended run log |
