#!/usr/bin/env python3
import csv
import argparse
import logging
import os
import re
import sys
from typing import Dict, List, Optional, Tuple

from taxonomy_constants import ALLOWED_CATEGORIES, VALID_TAG1, VALID_TAG2, VALID_TAG3

# ----------------------------
# Scale-oriented normalizer
# ----------------------------
# Features:
# - Streams input/output row by row (memory safe for large files)
# - Auto-generates *_normalized and *_review filenames
# - Supports CSV and TSV by delimiter sniffing
# - Uses lookup table + aliases + rule-based fallbacks
# - Applies allowlist + explicit blacklist + pattern blacklist for Category and tags
# - Optional batch mode with glob patterns
# - Writes a compact run summary to stdout
#
# NOTE: The '#CMPG' column (Mil / Civ / Gov / Pol operator-type split) is
#       intentionally left unchanged by this normalizer.  It is orthogonal to
#       the aviation taxonomy and is used by create_db_derivatives.py to
#       generate the derivative CSV files (aircraft-taxonomy-mil.csv, etc.).

logging.basicConfig(
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Canonical mapping lets you salvage a few common near-misses safely.
CATEGORY_CANONICAL_MAP = {
    "Biz Jet": "Business Jet",
    "Bizjet": "Business Jet",
    "Bizjets": "Business Jet",
    "Business Jets": "Business Jet",
    "Widebody": "Passenger - Widebody",
    "Narrowbody": "Passenger - Narrowbody",
    "Regional": "Regional Passenger",
    "Cargo": "Cargo Freighter",
    "Freighter": "Cargo Freighter",
}

BLACKLISTED_CATEGORIES = {
    "USAF",
    "Other Air Forces",
    "Toy Soldiers",
    "Police Forces",
    "Flying Doctors",
    "Oxcart",
    "United States Navy",
    "Historic",
    "As Seen on TV",
    "Coastguard",
    "GAF",
    "Jump Johnny Jump",
    "Aerial Firefighter",
    "Hired Gun",
    "Dictator Alert",
    "Governments",
    "United States Marine Corps",
    "Gunship",
    "Joe Cool",
    "RAF",
    "Ptolemy would be proud",
    "Distinctive",
    "Dogs with Jobs",
    "Other Navies",
    "Climate Crisis",
    "Special Forces",
    "Zoomies",
    "You came here in that thing?",
    "Big Hello",
    "Royal Navy Fleet Air Arm",
    "Army Air Corps",
    "Da Comrade",
    "Don't you know who I am?",
    "Vanity Plate",
    "Aerobatic Teams",
    "Perfectly Serviceable Aircraft",
    "Watch Me Fly",
    "Bizjets",
    "UAV",
    "Oligarch",
    "Ukraine",
    "Quango",
    "Jesus he Knows me",
    "UK National Police Air Service",
    "Football",
    "Nuclear",
    "CAP",
    "Head of State",
    "PIA",
    "Gas Bags",
    "Royal Aircraft",
    "Radiohead",
    "Medical Evac",
    "Air Ambo",
    "Aerial Survey",
    "Air Experience Flight",
    "Weather Recon",
}

BLACKLIST_PATTERNS = [
    r"https?://",
    r"www\.",
    # jokes / slogans / references
    r"\bjump\b",
    r"\bwatch me\b",
    r"\byou came here in that thing\b",
    r"\bbig hello\b",
    r"\bperfectly serviceable\b",
    r"\bdon't you know who i am\b",
    r"\bmust be nice\b",
    r"\bjoe cool\b",
    r"\bda comrade\b",
    r"\bptolemy\b",
    r"\bradiohead\b",
    r"\bdogs with jobs\b",
    r"\btoy soldiers\b",
    r"\bzoomies\b",
    r"\bas seen on tv\b",
    r"\bvanity plate\b",
    # political / opinion / commentary
    r"\bdictator\b",
    r"\bclimate crisis\b",
    r"\bman made climate change\b",
    r"\bfree and fair elections\b",
    r"\boligarch\b",
    r"\bquango\b",
    # operator / branch / service group
    r"\bair force\b",
    r"\bnavy\b",
    r"\bmarine corps\b",
    r"\barmy air corps\b",
    r"\broyal navy\b",
    r"\braf\b",
    r"\busaf\b",
    r"\bcoast ?guard\b",
    r"\bpolice\b",
    r"\bgovernment\b",
    r"\bgovernments\b",
    r"\bnational police\b",
    r"\bflying doctors\b",
    r"\bspecial forces\b",
    r"\bhead of state\b",
    # country / geopolitical labels
    r"\bukraine\b",
    r"\begypt\b",
    r"\bnigeria\b",
    r"\bqatar\b",
    r"\blibya\b",
    r"\bcolombia\b",
    r"\bunited states\b",
    # mission phrases that do not belong in base Category or tags
    r"\bmedical evac\b",
    r"\bair ambo\b",
    r"\baerial survey\b",
    r"\bweather recon\b",
    r"\bair experience flight\b",
]

CATEGORY_PATTERN_RE = [re.compile(p, re.IGNORECASE) for p in BLACKLIST_PATTERNS]
URL_RE = re.compile(r"^https?://", re.IGNORECASE)
PHRASEY_RE = re.compile(r"[!?]|([A-Za-z]+\s+){4,}[A-Za-z]+")

TAG_FIELDS = ("$Tag 1", "$#Tag 2", "$#Tag 3")
REQUIRED_LOOKUP_COLUMNS = {
    "match_key", "normalized_type", "category", "tag1", "tag2", "tag3"
}


def norm_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def norm_key(value: str) -> str:
    return norm_ws(value).casefold()


def canonicalize_category(value: str) -> str:
    value = norm_ws(value)
    return CATEGORY_CANONICAL_MAP.get(value, value)


def detect_delimiter(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(8192)
    if "\t" in sample and sample.count("\t") >= sample.count(","):
        return "\t"
    return ","


def get_output_paths(input_path: str) -> Tuple[str, str]:
    base, ext = os.path.splitext(input_path)
    return f"{base}_normalized{ext}", f"{base}_review{ext}"


def load_lookup(path: Optional[str]) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    if not path:
        return lookup
    delimiter = detect_delimiter(path)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        missing = REQUIRED_LOOKUP_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Lookup file missing required columns: {sorted(missing)}")
        for row in reader:
            key = norm_key(row.get("match_key", ""))
            if key:
                lookup[key] = {k: norm_ws(v) for k, v in row.items()}
    return lookup


def load_aliases(path: Optional[str]) -> Dict[str, str]:
    aliases: Dict[str, str] = {}
    if not path:
        return aliases
    delimiter = detect_delimiter(path)
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            raw = norm_key(row.get("raw_value", ""))
            key = norm_key(row.get("match_key", ""))
            if raw and key:
                aliases[raw] = key
    return aliases


def invalid_text_reason(value: str, allowed: Optional[set] = None) -> Optional[str]:
    raw = norm_ws(value)
    if not raw:
        return "empty"
    if allowed is not None and raw in allowed:
        return None
    if raw in BLACKLISTED_CATEGORIES:
        return "explicit_blacklist"
    if URL_RE.search(raw):
        return "url"
    for cre in CATEGORY_PATTERN_RE:
        if cre.search(raw):
            return "pattern_blacklist"
    if PHRASEY_RE.search(raw):
        return "long_phrase_or_reference"
    return "not_in_allowlist"


def resolve_category(original: str, lookup_category: str) -> Tuple[str, str, str]:
    original = norm_ws(original)
    canon = canonicalize_category(original)

    if canon in ALLOWED_CATEGORIES:
        if canon == original:
            return canon, "kept_existing", "allowed_category"
        return canon, "canonicalized_existing", "mapped_to_allowed_category"

    reason = invalid_text_reason(original)
    lookup_canon = canonicalize_category(lookup_category)
    if lookup_canon in ALLOWED_CATEGORIES:
        return lookup_canon, "overwritten_from_lookup", reason or "unknown_invalid_category"

    return "", "review_required", reason or "no_valid_lookup_category"


def resolve_tag(original: str, lookup_value: str, allowed: set, field_name: str) -> Tuple[str, str, str]:
    original = norm_ws(original)
    if original in allowed:
        return original, "kept_existing", "allowed_value"

    reason = invalid_text_reason(original, allowed=None)
    lookup_value = norm_ws(lookup_value)
    if lookup_value in allowed:
        return lookup_value, "overwritten_from_lookup", reason or f"invalid_{field_name}"

    # If original is invalid and lookup does not rescue it, blank it.
    return "", "review_required", reason or f"not_in_{field_name}_allowlist"


def match_lookup(row: Dict[str, str], lookup: Dict[str, Dict[str, str]], aliases: Dict[str, str]) -> Tuple[Optional[Dict[str, str]], str, str]:
    icao_type = norm_key(row.get("$ICAO Type", ""))
    type_name = norm_key(row.get("$Type", ""))

    if icao_type and icao_type in lookup:
        return lookup[icao_type], "icao_type", icao_type

    if type_name and type_name in lookup:
        return lookup[type_name], "type_exact", type_name

    if type_name and type_name in aliases:
        alias_key = aliases[type_name]
        if alias_key in lookup:
            return lookup[alias_key], "type_alias", alias_key

    if icao_type and icao_type in aliases:
        alias_key = aliases[icao_type]
        if alias_key in lookup:
            return lookup[alias_key], "icao_alias", alias_key

    return None, "none", ""


def infer_mission_override(row: Dict[str, str]) -> str:
    operator = norm_key(row.get("$Operator", ""))
    type_name = norm_key(row.get("$Type", ""))

    if any(x in operator for x in ("aeromedical", "air ambulance", "medical", "medevac", "rescue")):
        return "Air Ambulance"
    if "survey" in operator or "survey" in type_name:
        return "Aerial Survey"
    if any(x in operator for x in ("government", "executive", "head of state")):
        return "VIP Transport"
    if "fire" in operator:
        return "Aerial Firefighting"
    return ""


def ensure_fieldnames(reader_fieldnames: List[str], include_audit: bool = True) -> List[str]:
    base = list(reader_fieldnames)
    if not include_audit:
        return base
    extras = [
        "Normalized Type",
        "Mission Override",
        "Normalization Status",
        "Normalization Source",
        "Normalization Match Key",
        "Normalization Confidence",
        "Category Status",
        "Category Reason",
        "Tag 1 Status",
        "Tag 1 Reason",
        "Tag 2 Status",
        "Tag 2 Reason",
        "Tag 3 Status",
        "Tag 3 Reason",
    ]
    for col in extras:
        if col not in base:
            base.append(col)
    return base


def process_file(input_path: str, lookup: Dict[str, Dict[str, str]], aliases: Dict[str, str], no_audit_cols: bool = False) -> Tuple[str, str, Dict[str, int]]:
    delimiter = detect_delimiter(input_path)
    output_path, review_path = get_output_paths(input_path)
    stats = {
        "rows_total": 0,
        "rows_normalized": 0,
        "rows_review": 0,
        "matched_lookup": 0,
        "matched_alias": 0,
        "matched_type_exact": 0,
        "matched_icao": 0,
        "unmatched": 0,
    }

    with open(input_path, "r", encoding="utf-8-sig", newline="") as infile, \
         open(output_path, "w", encoding="utf-8", newline="") as outfile, \
         open(review_path, "w", encoding="utf-8", newline="") as reviewfile:

        reader = csv.DictReader(infile, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError(f"No header row found in {input_path}")

        fieldnames = ensure_fieldnames(list(reader.fieldnames), include_audit=not no_audit_cols)

        writer = csv.DictWriter(outfile, fieldnames=fieldnames, delimiter=delimiter, extrasaction="ignore")
        review_writer = csv.DictWriter(reviewfile, fieldnames=fieldnames, delimiter=delimiter, extrasaction="ignore")
        writer.writeheader()
        review_writer.writeheader()

        for row in reader:
            stats["rows_total"] += 1

            match, source, match_key = match_lookup(row, lookup, aliases)
            if source == "icao_type":
                stats["matched_icao"] += 1
                stats["matched_lookup"] += 1
            elif source == "type_exact":
                stats["matched_type_exact"] += 1
                stats["matched_lookup"] += 1
            elif source in {"type_alias", "icao_alias"}:
                stats["matched_alias"] += 1
                stats["matched_lookup"] += 1
            else:
                stats["unmatched"] += 1

            lookup_category = match.get("category", "") if match else ""
            lookup_tag1 = match.get("tag1", "") if match else ""
            lookup_tag2 = match.get("tag2", "") if match else ""
            lookup_tag3 = match.get("tag3", "") if match else ""
            normalized_type = match.get("normalized_type", "") if match else ""

            final_category, category_status, category_reason = resolve_category(
                row.get("Category", ""), lookup_category
            )
            final_tag1, tag1_status, tag1_reason = resolve_tag(
                row.get("$Tag 1", ""), lookup_tag1, VALID_TAG1, "tag1"
            )
            final_tag2, tag2_status, tag2_reason = resolve_tag(
                row.get("$#Tag 2", ""), lookup_tag2, VALID_TAG2, "tag2"
            )
            final_tag3, tag3_status, tag3_reason = resolve_tag(
                row.get("$#Tag 3", ""), lookup_tag3, VALID_TAG3, "tag3"
            )

            row["Category"] = final_category
            row["$Tag 1"] = final_tag1
            row["$#Tag 2"] = final_tag2
            row["$#Tag 3"] = final_tag3
            row["Normalized Type"] = normalized_type or norm_ws(row.get("$Type", ""))
            row["Mission Override"] = infer_mission_override(row)
            row["Normalization Source"] = source
            row["Normalization Match Key"] = match_key
            row["Category Status"] = category_status
            row["Category Reason"] = category_reason
            row["Tag 1 Status"] = tag1_status
            row["Tag 1 Reason"] = tag1_reason
            row["Tag 2 Status"] = tag2_status
            row["Tag 2 Reason"] = tag2_reason
            row["Tag 3 Status"] = tag3_status
            row["Tag 3 Reason"] = tag3_reason

            # A row is written to the normalized output when its category is
            # resolved to a valid taxonomy value.  Confidence reflects how
            # completely the row was filled in from the lookup table.
            fully_resolved = all([
                final_category,
                final_tag1,
                final_tag2,
                final_tag3,
                bool(normalized_type),
            ])

            if final_category:
                row["Normalization Status"] = "normalized"
                if fully_resolved and match:
                    row["Normalization Confidence"] = "high"
                elif match:
                    row["Normalization Confidence"] = "medium"
                else:
                    row["Normalization Confidence"] = "low"
                writer.writerow(row)
                stats["rows_normalized"] += 1
            else:
                row["Normalization Status"] = "review_required"
                row["Normalization Confidence"] = "low" if not match else "medium"
                review_writer.writerow(row)
                stats["rows_review"] += 1

    return output_path, review_path, stats


def iter_input_files(inputs: List[str]) -> List[str]:
    import glob
    files: List[str] = []
    for item in inputs:
        expanded = sorted(glob.glob(item))
        if expanded:
            files.extend(expanded)
        elif os.path.isfile(item):
            files.append(item)
    deduped = []
    seen = set()
    for f in files:
        absf = os.path.abspath(f)
        if absf not in seen:
            seen.add(absf)
            deduped.append(f)
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser(description="Scale-oriented aircraft normalizer")
    parser.add_argument("inputs", nargs="+", help="Input CSV/TSV file(s) or glob(s)")
    parser.add_argument("--lookup", required=True, help="Verified lookup CSV/TSV")
    parser.add_argument("--aliases", help="Aliases CSV/TSV")
    parser.add_argument("--no-audit-cols", action="store_true",
                        help="Suppress the 13 diagnostic audit columns from outputs (suitable for production CSV)")
    args = parser.parse_args()

    try:
        lookup = load_lookup(args.lookup)
        aliases = load_aliases(args.aliases)
    except Exception as exc:
        logger.error("Loading support files failed: %s", exc)
        return 2

    files = iter_input_files(args.inputs)
    if not files:
        logger.error("No input files found.")
        return 2

    total = {
        "rows_total": 0,
        "rows_normalized": 0,
        "rows_review": 0,
        "matched_lookup": 0,
        "matched_alias": 0,
        "matched_type_exact": 0,
        "matched_icao": 0,
        "unmatched": 0,
    }

    for path in files:
        try:
            output_path, review_path, stats = process_file(path, lookup, aliases, no_audit_cols=args.no_audit_cols)
        except Exception as exc:
            logger.error("Processing %s failed: %s", path, exc)
            continue

        logger.info("Processed: %s", path)
        logger.info("  Normalized: %s", output_path)
        logger.info("  Review:     %s", review_path)
        logger.info(
            "  Stats: total=%d normalized=%d review=%d matched_lookup=%d unmatched=%d",
            stats['rows_total'], stats['rows_normalized'], stats['rows_review'],
            stats['matched_lookup'], stats['unmatched'],
        )

        for key in total:
            total[key] += stats.get(key, 0)

    logger.info(
        "Run summary: total_rows=%d normalized=%d review=%d "
        "matched_lookup=%d matched_icao=%d matched_type_exact=%d matched_alias=%d unmatched=%d",
        total['rows_total'], total['rows_normalized'], total['rows_review'],
        total['matched_lookup'], total['matched_icao'],
        total['matched_type_exact'], total['matched_alias'], total['unmatched'],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
