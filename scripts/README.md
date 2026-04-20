# Scripts

This folder contains all automation scripts for the aircraft taxonomy pipeline.

## Directory contract

All scripts assume they are run from the **repository root** (not from inside `scripts/`).

| Path | Role |
| --- | --- |
| `data/` | Operational CSV datasets — the source-of-truth aircraft records. |
| `taxonomy/` | Taxonomy reference files (lookup seed, canonical lookup / aliases). |
| `cache/public_sources/` | Downloaded public aircraft database snapshots (gitignored). |
| `build/weekly_update/` | Intermediate pipeline artefacts from the weekly run (gitignored). |
| `review/` | Committed review-queue CSVs produced by weekly normalisation runs. |

## Script catalogue

### Data-hygiene / CI scripts

| Script | Purpose |
| --- | --- |
| `check_main_databases.py` | Validates `data/plane-alert-db.csv` — checks for duplicate ICAOs and invalid hex codes. |
| `check_categories.py` | Verifies that every Category in `data/plane-alert-db.csv` appears in `data/plane-alert-categories.csv`. |
| `check_invalid_derivatives.py` | Used by CI to detect hand-edited derivative files. |
| `validate_schema.py` | Schema-contract checker. Validates column headers, duplicate keys, and taxonomy values in lookup, aliases, and data files. |

### Publishing / derivative scripts

| Script | Purpose |
| --- | --- |
| `create_db_derivatives.py` | Splits `data/plane-alert-db.csv` by `#CMPG` into `data/plane-alert-{civ,mil,pol,gov}.csv`. |
| `export_categories.py` | Exports the unique Category list to `data/plane-alert-categories.csv`. |
| `update_readme.py` | Regenerates `README.md` from `readme.mustache` with live row counts. |

### Taxonomy normalisation pipeline scripts

| Script | Purpose |
| --- | --- |
| `normalize_aircraft_v5.py` | Core normaliser. Maps each aircraft's `$ICAO Type` / `$Type` field to the canonical taxonomy. |
| `expand_aircraft_aliases_v2.py` | Expands the alias seed against public metadata to produce a broader alias set. |
| `validate_aircraft_references.py` | Scores lookup / alias rows against cached public metadata. Produces review queues. |
| `auto_promote_aircraft_references.py` | Promotes high-confidence review rows into the canonical lookup / aliases. |
| `sync_public_aircraft_sources.py` | Downloads fresh public aircraft reference data into `cache/public_sources/`. |
| `promote_reviewed_lookup_rows.py` | Merges a manually reviewed lookup CSV into `taxonomy/aircraft_type_lookup.csv`. |
| `weekly_update_pipeline_v3.py` | Orchestrates the full weekly flow: sync → expand → validate → promote → publish → normalise. |

---

## Aviation-taxonomy normalizer (`normalize_aircraft_v5.py`)

This script processes one or more CSV files and produces:

- `*_normalized.csv` — rows whose `Category` was resolved to a valid taxonomy value.
- `*_review.csv` — rows that still need a `Category` assigned.

### Taxonomy reference files (live in `taxonomy/`)

| File | Purpose |
| --- | --- |
| `aircraft_type_lookup.csv` | Published canonical lookup. Maps ICAO type designators to taxonomy values. Required columns: `match_key`, `normalized_type`, `category`, `tag1`, `tag2`, `tag3`. |
| `aircraft_type_aliases.csv` | Published canonical aliases. Maps free-text spellings to a canonical `match_key`. Required columns: `raw_value`, `match_key`. |
| `aircraft_lookup_seed.csv` | Manually curated base lookup (never auto-overwritten). |
| `aircraft_aliases.csv` | Manually curated base aliases (never auto-overwritten). |

### Allowed values

**Category** (24 values):
`AEW&C`, `Attack / Strike`, `Business Jet`, `Cargo Freighter`, `Electronic Warfare`,
`Fighter / Interceptor`, `Helicopter - Attack`, `Helicopter - Maritime`,
`Helicopter - Transport`, `Helicopter - Utility`, `ISR / Surveillance`,
`Maritime Patrol`, `Passenger - Narrowbody`, `Passenger - Widebody`,
`Regional Passenger`, `Special Mission`, `Strategic Airlift`, `Tactical Airlift`,
`Tanker`, `Trainer`, `UAV - Combat`, `UAV - Recon`, `UAV - Utility`, `Utility`

**Tag 1** (primary mission):
`Tactical Transport`, `Strategic Transport`, `Maritime Patrol`, `ISR`, `Early Warning`,
`Air Superiority`, `Strike`, `Close Air Support`, `Refueling`, `Training`,
`Utility`, `Electronic Warfare`

**Tag 2** (capability / configuration):
`STOL`, `Long Range`, `Short Runway`, `Heavy Lift`, `Medium Lift`, `Multi-Role`,
`All-Weather`, `High Endurance`, `Aerial Refueling`, `Carrier Capable`,
`Amphibious`, `Basic Trainer`, `Light Lift`, `Low Altitude`

**Tag 3** (propulsion / airframe):
`Twin Turboprop`, `Turboprop`, `Twin Engine`, `Quad Engine`, `Jet`, `High Wing`,
`Low Wing`, `Rear Ramp`, `Side Door`, `Pressurized`, `Sensor Suite`,
`Modular Cabin`, `Single Engine`, `Rotorcraft`

### Usage

```bash
# Run normaliser (produces data/plane-alert-db_normalized.csv + data/plane-alert-db_review.csv)
python scripts/normalize_aircraft_v5.py data/plane-alert-db.csv \
    --lookup taxonomy/aircraft_type_lookup.csv \
    --aliases taxonomy/aircraft_type_aliases.csv

# Production output — no diagnostic audit columns
python scripts/normalize_aircraft_v5.py data/plane-alert-db.csv \
    --lookup taxonomy/aircraft_type_lookup.csv \
    --aliases taxonomy/aircraft_type_aliases.csv \
    --no-audit-cols
```

After running, inspect `data/plane-alert-db_review.csv`. For each unresolved row:

1. Add its ICAO type to `taxonomy/aircraft_type_lookup.csv` (and the seed), or
2. Add an alias for the free-text `$Type` value to `taxonomy/aircraft_type_aliases.csv` (and the seed).

Then re-run until the review file is empty (or acceptably small).

When running `weekly_update_pipeline_v3.py`, generated `plane-alert-*_review.csv` files are moved into `review/`.

### Important: `#CMPG` passthrough

The `#CMPG` column (`Mil` / `Civ` / `Gov` / `Pol`) is **intentionally not modified** by the
normaliser. It reflects the operator type and is used by `create_db_derivatives.py` to split
the database into `data/plane-alert-{mil,civ,gov,pol}.csv`.

---

## Validate schema contracts

```bash
python scripts/validate_schema.py \
    --lookup taxonomy/aircraft_type_lookup.csv \
    --aliases taxonomy/aircraft_type_aliases.csv \
    --data-files data/plane-alert-db.csv data/plane-alert-pia.csv
```

---

## Full weekly pipeline

See [docs/RUNBOOK.md](../docs/RUNBOOK.md) for the complete operator guide.

```bash
python scripts/sync_public_aircraft_sources.py --cache-dir cache/public_sources

python scripts/weekly_update_pipeline_v3.py \
    --workspace . \
    --seed-aliases taxonomy/aircraft_aliases.csv \
    --seed-lookup taxonomy/aircraft_lookup_seed.csv \
    --no-audit-cols
```
