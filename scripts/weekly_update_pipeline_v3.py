#!/usr/bin/env python3
"""
Weekly aircraft reference + database refresh pipeline, with validation + auto-promotion.

Workflow
1) optional public cache refresh
2) alias expansion
3) validation of lookup + aliases against cached local public metadata
4) auto-promotion of review rows above confidence thresholds
5) publish aircraft_type_aliases.csv and aircraft_type_lookup.csv if content changed
6) rerun normalizer against plane_alert_*.csv when references changed
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def backup_if_exists(path: Path) -> Optional[Path]:
    if not path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_suffix(path.suffix + f".{stamp}.bak")
    shutil.copy2(path, backup)
    return backup

def replace_if_changed(src: Path, dest: Path) -> bool:
    if not src.exists():
        raise FileNotFoundError(src)
    if dest.exists() and sha256_file(src) == sha256_file(dest):
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup_if_exists(dest)
    shutil.copy2(src, dest)
    return True

def run(cmd: list[str], cwd: Optional[Path] = None) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)

def main() -> int:
    p = argparse.ArgumentParser(description="Weekly aircraft update pipeline with validation and auto-promotion")
    p.add_argument("--workspace", default=".")
    p.add_argument("--normalizer", default="scripts/normalize_aircraft_v5.py")
    p.add_argument("--alias-expander", default="scripts/expand_aircraft_aliases_v2.py")
    p.add_argument("--validator", default="scripts/validate_aircraft_references.py")
    p.add_argument("--promoter", default="scripts/auto_promote_aircraft_references.py")
    p.add_argument("--sync-script", default="scripts/sync_public_aircraft_sources.py")
    p.add_argument("--seed-aliases", default="taxonomy/aircraft_aliases.csv")
    p.add_argument("--seed-lookup", default="taxonomy/aircraft_lookup_seed.csv")
    p.add_argument("--cache-dir", default="cache/public_sources")
    p.add_argument("--skip-sync", action="store_true")
    p.add_argument("--no-audit-cols", action="store_true")
    p.add_argument("--force-refresh", action="store_true")
    p.add_argument("--lookup-threshold", type=float, default=0.70)
    p.add_argument("--alias-threshold", type=float, default=0.75)
    args = p.parse_args()

    ws = Path(args.workspace).resolve()
    cache_dir = (ws / args.cache_dir).resolve()
    outdir = (ws / "build" / "weekly_update").resolve()
    review_dir = (ws / "review").resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    published_aliases = ws / "taxonomy" / "aircraft_type_aliases.csv"
    published_lookup = ws / "taxonomy" / "aircraft_type_lookup.csv"

    if not args.skip_sync:
        run([sys.executable, str(ws / args.sync_script), "--cache-dir", str(cache_dir)], cwd=ws)

    public_csvs = list(cache_dir.glob("*.csv")) + list(cache_dir.glob("*.tsv"))

    expand_cmd = [
        sys.executable, str(ws / args.alias_expander),
        str(ws / args.seed_aliases),
        "--output-dir", str(outdir),
    ]
    if public_csvs:
        expand_cmd += ["--public-metadata", *[str(p) for p in public_csvs]]
    run(expand_cmd, cwd=ws)

    verified_expanded = outdir / f"{Path(args.seed_aliases).stem}_verified_expanded_for_normalizer.csv"
    if not verified_expanded.exists():
        verified_expanded = outdir / "aircraft_type_aliases_verified_expanded_for_normalizer.csv"

    validate_cmd = [
        sys.executable, str(ws / args.validator),
        "--lookup", str(published_lookup),
        "--aliases", str(published_aliases),
        "--output-dir", str(outdir),
    ]
    if public_csvs:
        validate_cmd += ["--public-metadata", *[str(p) for p in public_csvs]]
    run(validate_cmd, cwd=ws)

    promote_cmd = [
        sys.executable, str(ws / args.promoter),
        "--lookup-existing", str(published_lookup),
        "--aliases-existing", str(published_aliases),
        "--lookup-review", str(outdir / "aircraft_type_lookup_review.csv"),
        "--aliases-review", str(outdir / "aircraft_type_aliases_review.csv"),
        "--lookup-threshold", str(args.lookup_threshold),
        "--alias-threshold", str(args.alias_threshold),
        "--output-dir", str(outdir),
    ]
    run(promote_cmd, cwd=ws)

    aliases_changed = replace_if_changed(
        outdir / "aircraft_type_aliases_promoted_for_normalizer.csv",
        published_aliases,
    )
    lookup_changed = replace_if_changed(
        outdir / "aircraft_type_lookup_promoted.csv",
        published_lookup,
    )
    refs_changed = aliases_changed or lookup_changed

    SKIP_DATA_STEMS = {"plane-alert-categories", "plane-alert-search-terms-to-do"}
    plane_files = sorted(
        f for f in ws.glob("data/plane-alert-*.csv")
        if f.stem not in SKIP_DATA_STEMS
    )
    refreshed = 0
    if refs_changed or args.force_refresh:
        for plane_file in plane_files:
            cmd = [
                sys.executable, str(ws / args.normalizer),
                str(plane_file),
                "--lookup", str(published_lookup),
                "--aliases", str(published_aliases),
            ]
            if args.no_audit_cols:
                cmd.append("--no-audit-cols")
            run(cmd, cwd=ws)

            normalized = plane_file.with_name(plane_file.stem + "_normalized" + plane_file.suffix)
            review = plane_file.with_name(plane_file.stem + "_review" + plane_file.suffix)
            if normalized.exists():
                backup_if_exists(plane_file)
                shutil.move(str(normalized), str(plane_file))
                refreshed += 1
            if review.exists():
                shutil.move(str(review), str(review_dir / review.name))

    manifest = {
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "aliases_changed": aliases_changed,
        "lookup_changed": lookup_changed,
        "refs_changed": refs_changed,
        "plane_alert_files_found": len(plane_files),
        "plane_alert_files_refreshed": refreshed,
        "published_aliases": str(published_aliases),
        "published_lookup": str(published_lookup),
        "lookup_threshold": args.lookup_threshold,
        "alias_threshold": args.alias_threshold,
    }
    (outdir / "weekly_update_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
