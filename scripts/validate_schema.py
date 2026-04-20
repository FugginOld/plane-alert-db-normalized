#!/usr/bin/env python3
"""
Schema contract validator for the aircraft taxonomy pipeline.

Checks that:
  - taxonomy/aircraft_type_lookup.csv has all required columns and no duplicate keys.
  - taxonomy/aircraft_type_aliases.csv has all required columns and no duplicate (raw_value, match_key) pairs.
  - Each data file (e.g. data/aircraft-taxonomy-db.csv) has all required columns, no
    duplicate ICAO codes, and only uses Category values from the allowed taxonomy set.

Exits with a non-zero status code when any contract is violated.

Usage:
    python scripts/validate_schema.py \\
        --lookup taxonomy/aircraft_type_lookup.csv \\
        --aliases taxonomy/aircraft_type_aliases.csv \\
        --data-files data/aircraft-taxonomy-db.csv data/aircraft-taxonomy-pia.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from pathlib import Path
from typing import List, Sequence

from taxonomy_constants import ALLOWED_CATEGORIES

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

LOOKUP_REQUIRED = {"match_key", "normalized_type", "category", "tag1", "tag2", "tag3"}
ALIAS_REQUIRED = {"raw_value", "match_key"}
DATA_REQUIRED = {"$ICAO", "$Registration", "$Operator", "$Type", "$ICAO Type", "#CMPG", "Category"}

MATCHKEY_RE = re.compile(r"^[A-Z0-9]{2,5}$")  # ICAO type designator: 2–5 uppercase alphanumeric chars
WS_RE = re.compile(r"\s+")


def norm_ws(value: str) -> str:
    return WS_RE.sub(" ", (value or "").strip())


def sniff_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8-sig", errors="ignore")[:8192]
    return "\t" if sample.count("\t") > sample.count(",") else ","


def read_csv_rows(path: Path) -> list[dict]:
    delim = sniff_delimiter(path)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delim))


def check_required_columns(path: Path, rows: list[dict], required: set[str]) -> list[str]:
    errors: list[str] = []
    if not rows:
        errors.append(f"{path}: file is empty or has no header row")
        return errors
    actual = set(rows[0].keys())
    missing = required - actual
    if missing:
        errors.append(f"{path}: missing required columns: {sorted(missing)}")
    return errors


def validate_lookup(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        errors.append(f"{path}: file not found")
        return errors
    rows = read_csv_rows(path)
    errors.extend(check_required_columns(path, rows, LOOKUP_REQUIRED))
    if errors:
        return errors

    seen_keys: dict[str, int] = {}
    for i, row in enumerate(rows, start=2):
        key = norm_ws(row.get("match_key", "")).upper()
        if not key:
            errors.append(f"{path} row {i}: empty match_key")
            continue
        if not MATCHKEY_RE.match(key):
            errors.append(f"{path} row {i}: invalid match_key format '{key}' (expected 2-5 uppercase alphanumeric chars)")
        if key in seen_keys:
            errors.append(f"{path} row {i}: duplicate match_key '{key}' (first seen at row {seen_keys[key]})")
        else:
            seen_keys[key] = i

        category = norm_ws(row.get("category", ""))
        if category and category not in ALLOWED_CATEGORIES:
            errors.append(f"{path} row {i}: unrecognised category '{category}' for match_key '{key}'")
    return errors


def validate_aliases(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        errors.append(f"{path}: file not found")
        return errors
    rows = read_csv_rows(path)
    errors.extend(check_required_columns(path, rows, ALIAS_REQUIRED))
    if errors:
        return errors

    seen_pairs: set[tuple[str, str]] = set()
    for i, row in enumerate(rows, start=2):
        raw = norm_ws(row.get("raw_value", "")).casefold()
        key = norm_ws(row.get("match_key", "")).upper()
        if not raw:
            errors.append(f"{path} row {i}: empty raw_value")
            continue
        if not key:
            errors.append(f"{path} row {i}: empty match_key")
            continue
        if not MATCHKEY_RE.match(key):
            errors.append(f"{path} row {i}: invalid match_key format '{key}' for alias '{raw}'")
        pair = (raw, key)
        if pair in seen_pairs:
            errors.append(f"{path} row {i}: duplicate alias pair ('{raw}', '{key}')")
        else:
            seen_pairs.add(pair)
    return errors


def validate_data_file(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        errors.append(f"{path}: file not found")
        return errors
    rows = read_csv_rows(path)
    errors.extend(check_required_columns(path, rows, DATA_REQUIRED))
    if errors:
        return errors

    seen_icao: dict[str, int] = {}
    invalid_categories: list[str] = []
    for i, row in enumerate(rows, start=2):
        icao = norm_ws(row.get("$ICAO", "")).upper()
        if not icao:
            errors.append(f"{path} row {i}: empty $ICAO")
            continue
        if icao in seen_icao:
            errors.append(f"{path} row {i}: duplicate $ICAO '{icao}' (first at row {seen_icao[icao]})")
        else:
            seen_icao[icao] = i

        category = norm_ws(row.get("Category", ""))
        if category and category not in ALLOWED_CATEGORIES:
            invalid_categories.append(f"row {i}: '{category}'")

    if invalid_categories:
        sample = invalid_categories[:5]
        suffix = f" (+{len(invalid_categories) - 5} more)" if len(invalid_categories) > 5 else ""
        errors.append(
            f"{path}: {len(invalid_categories)} row(s) with unrecognised Category values — "
            + ", ".join(sample) + suffix
        )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate aircraft taxonomy schema contracts")
    p.add_argument("--lookup", default="taxonomy/aircraft_type_lookup.csv",
                   help="Canonical lookup CSV")
    p.add_argument("--aliases", default="taxonomy/aircraft_type_aliases.csv",
                   help="Canonical aliases CSV")
    p.add_argument("--data-files", nargs="*", default=[],
                   help="Data CSV files to validate (e.g. data/aircraft-taxonomy-db.csv)")
    p.add_argument("--strict", action="store_true",
                   help="Treat data-file category violations as errors (default: warnings)")
    args = p.parse_args(argv)

    all_errors: list[str] = []
    all_warnings: list[str] = []

    # Validate taxonomy reference files
    all_errors.extend(validate_lookup(Path(args.lookup)))
    all_errors.extend(validate_aliases(Path(args.aliases)))

    # Validate each data file
    for data_path_str in args.data_files:
        data_path = Path(data_path_str)
        data_errors = validate_data_file(data_path)
        if args.strict:
            all_errors.extend(data_errors)
        else:
            # Category violations in data files are warnings, not hard errors
            hard = [e for e in data_errors if "unrecognised Category" not in e]
            soft = [e for e in data_errors if "unrecognised Category" in e]
            all_errors.extend(hard)
            all_warnings.extend(soft)

    for warning in all_warnings:
        logger.warning(warning)

    if all_errors:
        for error in all_errors:
            logger.error(error)
        logger.error("Schema validation FAILED: %d error(s), %d warning(s).", len(all_errors), len(all_warnings))
        return 1

    logger.info(
        "Schema validation PASSED: lookup=%s, aliases=%s, data_files=%s, warnings=%d.",
        args.lookup, args.aliases, args.data_files or [], len(all_warnings),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
