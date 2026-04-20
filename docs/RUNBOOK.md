# Aircraft Taxonomy Maintenance — Operational Runbook

This runbook describes the day-to-day and weekly operations for maintaining the aviation
taxonomy used to normalise the plane-alert-db dataset.

---

## Directory contract

| Path | Role | Committed? |
| --- | --- | --- |
| `data/` | Operational CSV datasets (source-of-truth aircraft records) | ✅ Yes |
| `taxonomy/` | Taxonomy reference files (lookup seed, canonical lookup/aliases) | ✅ Yes |
| `cache/public_sources/` | Downloaded public aircraft database snapshots | ❌ No (gitignored) |
| `build/weekly_update/` | Intermediate pipeline artefacts from the weekly run | ❌ No (gitignored) |
| `review/` | Review-queue CSV outputs from normalisation runs | ✅ Yes |
| `scripts/` | All automation scripts | ✅ Yes |
| `docs/` | Documentation | ✅ Yes |

---

## File roles

### taxonomy/ — taxonomy reference files

| File | Role | Mutated by |
| --- | --- | --- |
| `aircraft_lookup_seed.csv` | Manually curated ICAO designator → taxonomy mapping. Never auto-overwritten. | Human editors |
| `aircraft_aliases.csv` | Manually curated free-text alias → ICAO designator mapping. | Human editors |
| `aircraft_type_lookup.csv` | Published canonical lookup. Starts as a copy of the seed; grows via auto-promotion each week. | `weekly_update_pipeline_v3.py` |
| `aircraft_type_aliases.csv` | Published canonical aliases. Starts as a copy of the aliases seed; grows via auto-promotion. | `weekly_update_pipeline_v3.py` |
| `aliases_ambiguous_seed.csv` | Aliases flagged as ambiguous (one name maps to several ICAO types). For human review. | Human editors |

### data/ — operational aircraft records

| File | Role |
| --- | --- |
| `plane-alert-db.csv` | Main aircraft database (source of truth). Edit this file directly. |
| `plane-alert-pia.csv` | Privacy ICAO Address (PIA) aircraft. |
| `plane-alert-wip.csv` | Work-in-progress aircraft candidates. |
| `plane-alert-civ.csv` | Auto-generated: civilian aircraft (CMPG=Civ). |
| `plane-alert-mil.csv` | Auto-generated: military aircraft (CMPG=Mil). |
| `plane-alert-pol.csv` | Auto-generated: police aircraft (CMPG=Pol). |
| `plane-alert-gov.csv` | Auto-generated: government aircraft (CMPG=Gov). |
| `plane-alert-categories.csv` | Auto-generated: unique Category values sorted by frequency. |

> **Important:** Only edit `plane-alert-db.csv` and `plane-alert-pia.csv` directly.
> All other `data/plane-alert-*.csv` files are regenerated automatically by GitHub Actions.

---

## Weekly update pipeline

### Overview

The weekly pipeline (`.github/workflows/weekly_taxonomy_update.yml`) runs every Sunday at
04:00 UTC. It can also be triggered manually via the GitHub Actions UI.

**Pipeline stages:**

```text
sync_public_aircraft_sources.py
    ↓ downloads → cache/public_sources/
weekly_update_pipeline_v3.py
    ├─ expand_aircraft_aliases_v2.py
    │    reads  taxonomy/aircraft_aliases.csv + cache/public_sources/*.csv
    │    writes build/weekly_update/*_verified_expanded_for_normalizer.csv
    ├─ validate_aircraft_references.py
    │    reads  taxonomy/aircraft_type_lookup.csv + taxonomy/aircraft_type_aliases.csv
    │    writes build/weekly_update/aircraft_type_lookup_review.csv
    │            build/weekly_update/aircraft_type_aliases_review.csv
    ├─ auto_promote_aircraft_references.py
    │    reads  taxonomy/aircraft_type_lookup.csv (existing canonical)
    │            taxonomy/aircraft_type_aliases.csv (existing canonical)
    │            build/weekly_update/aircraft_type_lookup_review.csv
    │            build/weekly_update/aircraft_type_aliases_review.csv
    │    writes build/weekly_update/aircraft_type_lookup_promoted.csv
    │            build/weekly_update/aircraft_type_aliases_promoted_for_normalizer.csv
    │            build/weekly_update/aircraft_promotion_report.json
    ├─ publishes if changed:
    │    taxonomy/aircraft_type_lookup.csv
    │    taxonomy/aircraft_type_aliases.csv
    └─ normalize_aircraft_v5.py (only runs when canonical files changed, or --force-refresh)
         reads  taxonomy/aircraft_type_lookup.csv
                 taxonomy/aircraft_type_aliases.csv
         writes every data/plane-alert-*.csv in place
                except data/plane-alert-categories.csv
                and data/plane-alert-search-terms-to-do.csv
                (for example: data/plane-alert-db.csv, data/plane-alert-pia.csv,
                 data/plane-alert-wip.csv, and any existing civ/mil/pol/gov derivatives)
         writes review queues to review/plane-alert-*_review.csv
```

In GitHub Actions, the weekly workflow commits updates for:

- `taxonomy/aircraft_type_lookup.csv`
- `taxonomy/aircraft_type_aliases.csv`
- `data/plane-alert-db.csv`
- `data/plane-alert-pia.csv`
- `data/plane-alert-wip.csv`

Derivative outputs (`data/plane-alert-civ.csv`, `data/plane-alert-mil.csv`,
`data/plane-alert-pol.csv`, `data/plane-alert-gov.csv`, and
`data/plane-alert-categories.csv`) are produced by derivative-generation workflows.

### Confidence thresholds

| Queue | Default threshold | Meaning |
| --- | --- | --- |
| Lookup promotion | 0.70 | Row added to canonical lookup only if scored ≥ 0.70 |
| Alias promotion | 0.75 | Alias added to canonical aliases only if scored ≥ 0.75 |

Adjust via `--lookup-threshold` / `--alias-threshold` arguments.

---

## Running the pipeline manually

### Prerequisites

```bash
pip install -r scripts/requirements.txt
```

### Full weekly run (local)

```bash
# 1. Download latest public source caches
python scripts/sync_public_aircraft_sources.py --cache-dir cache/public_sources

# 2. Run the pipeline
python scripts/weekly_update_pipeline_v3.py \
    --workspace . \
    --normalizer scripts/normalize_aircraft_v5.py \
    --alias-expander scripts/expand_aircraft_aliases_v2.py \
    --validator scripts/validate_aircraft_references.py \
    --promoter scripts/auto_promote_aircraft_references.py \
    --seed-aliases taxonomy/aircraft_aliases.csv \
    --seed-lookup taxonomy/aircraft_lookup_seed.csv \
    --no-audit-cols
```

### Skip network download (use existing cache)

```bash
python scripts/weekly_update_pipeline_v3.py \
    --workspace . \
    --skip-sync \
    --seed-aliases taxonomy/aircraft_aliases.csv \
    --seed-lookup taxonomy/aircraft_lookup_seed.csv \
    --no-audit-cols
```

### Force re-normalisation even if references are unchanged

```bash
python scripts/weekly_update_pipeline_v3.py --workspace . --force-refresh --no-audit-cols
```

### Normalise a single file manually

```bash
python scripts/normalize_aircraft_v5.py data/plane-alert-db.csv \
    --lookup taxonomy/aircraft_type_lookup.csv \
    --aliases taxonomy/aircraft_type_aliases.csv \
    --no-audit-cols
```

Review `data/plane-alert-db_review.csv` for rows the normaliser could not classify.

---

## Adding new taxonomy entries

### Adding a new ICAO type to the lookup

1. Edit `taxonomy/aircraft_lookup_seed.csv` and `taxonomy/aircraft_type_lookup.csv` (both files).
2. Required columns: `match_key,normalized_type,category,tag1,tag2,tag3`
3. `match_key` must be 2–5 uppercase alphanumeric characters (ICAO type designator).
4. `category` must be one of the 24 allowed values (see `scripts/normalize_aircraft_v5.py`).
5. Run `python scripts/validate_schema.py` to confirm no schema errors.
6. Open a PR.

### Adding a new alias for an existing type

1. Edit `taxonomy/aircraft_aliases.csv` and `taxonomy/aircraft_type_aliases.csv` (both files).
2. Required columns: `raw_value,match_key`
3. `raw_value` is the free-text spelling (case-insensitive).
4. `match_key` is the ICAO type designator already present in the lookup.
5. Run `python scripts/validate_schema.py` to confirm no schema errors.

### Promoting reviewed rows manually

```bash
python scripts/promote_reviewed_lookup_rows.py path/to/reviewed_lookup.csv \
    --target taxonomy/aircraft_type_lookup.csv
```

---

## Validating schema contracts

```bash
python scripts/validate_schema.py \
    --lookup taxonomy/aircraft_type_lookup.csv \
    --aliases taxonomy/aircraft_type_aliases.csv \
    --data-files data/plane-alert-db.csv data/plane-alert-pia.csv
```

Use `--strict` to treat Category violations in data files as hard errors.

---

## Inspecting weekly run artefacts

After each weekly run, build artefacts land in `build/weekly_update/`:

| File | Contents |
| --- | --- |
| `aircraft_type_lookup_review.csv` | Lookup rows that need human review |
| `aircraft_type_aliases_review.csv` | Alias rows that need human review |
| `aircraft_type_lookup_promoted.csv` | Final promoted lookup (becomes canonical) |
| `aircraft_type_aliases_promoted_for_normalizer.csv` | Final promoted aliases (becomes canonical) |
| `aircraft_type_lookup_promoted_candidates.csv` | Rows that were promoted this run |
| `aircraft_type_lookup_promotion_skipped.csv` | Rows skipped (below threshold or already exist) |
| `aircraft_promotion_report.json` | Promotion statistics |
| `weekly_update_manifest.json` | Full pipeline run summary |

These files are uploaded as GitHub Actions artifacts after each scheduled run.

---

## Troubleshooting

### "Lookup missing required columns"

The `aircraft_type_lookup.csv` or seed has a missing column header.
Required: `match_key,normalized_type,category,tag1,tag2,tag3`.

### "Aliases missing required columns"

The `aircraft_type_aliases.csv` or aliases seed is missing a column.
Required: `raw_value,match_key`.

### No files normalised after a weekly run

Check `build/weekly_update/weekly_update_manifest.json` — if `refs_changed` is `false`
and `force_refresh` was not set, no normalisation runs. Use `--force-refresh` or manually
edit the canonical files to trigger re-normalisation.

### Review queue is large

Large review queues mean many ICAO types in the lookup have no matching evidence in the
cached public metadata. Options:

- Re-run `sync_public_aircraft_sources.py` to refresh the cache.
- Manually review `aircraft_type_lookup_review.csv` and add entries directly to the seed.
- Lower the lookup threshold (`--lookup-threshold 0.5`) with caution.

---

## Rollback

### Rollback a canonical reference update

The weekly pipeline backs up the canonical files before overwriting them:

```text
taxonomy/aircraft_type_lookup.csv.<timestamp>.bak
taxonomy/aircraft_type_aliases.csv.<timestamp>.bak
```

To restore:

```bash
cp taxonomy/aircraft_type_lookup.csv.20260419T040000Z.bak taxonomy/aircraft_type_lookup.csv
cp taxonomy/aircraft_type_aliases.csv.20260419T040000Z.bak taxonomy/aircraft_type_aliases.csv
```

### Rollback a data file normalisation

Data files are similarly backed up before in-place replacement:

```text
data/plane-alert-db.csv.<timestamp>.bak
```

Restore the same way, then commit.
