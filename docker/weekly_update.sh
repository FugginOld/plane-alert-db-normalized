#!/bin/bash
# Weekly aircraft taxonomy update — runs inside the Docker container.
#
# Performs the full weekly pipeline:
#   1. Download fresh public aircraft reference data into cache/public_sources/
#   2. Expand aliases, validate and auto-promote taxonomy references
#   3. Re-normalise data/aircraft-taxonomy-*.csv when references have changed
#
# All output is written to both stdout/stderr (captured by journald when run
# via the systemd service) and appended to logs/weekly_aircraft_update.log
# (which is persisted on the host via a bind mount).
#
# Environment variables:
#   WORKSPACE   Path to the repository root inside the container.
#               Defaults to /workspace.

set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
LOG_DIR="${WORKSPACE}/logs"
LOG_FILE="${LOG_DIR}/weekly_aircraft_update.log"

mkdir -p "${LOG_DIR}"

# Redirect all output to both the terminal (journald) and the log file.
exec > >(tee -a "${LOG_FILE}") 2>&1

echo "========================================"
echo "aircraft-taxonomy weekly update started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "========================================"

python "${WORKSPACE}/scripts/weekly_update_pipeline_v3.py" \
    --workspace "${WORKSPACE}" \
    --normalizer scripts/normalize_aircraft_v5.py \
    --alias-expander scripts/expand_aircraft_aliases_v2.py \
    --validator scripts/validate_aircraft_references.py \
    --promoter scripts/auto_promote_aircraft_references.py \
    --seed-aliases taxonomy/aircraft_aliases.csv \
    --seed-lookup taxonomy/aircraft_lookup_seed.csv \
    --no-audit-cols

echo "========================================"
echo "aircraft-taxonomy weekly update finished: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "========================================"
