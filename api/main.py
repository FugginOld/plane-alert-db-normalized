"""aircraft-taxonomy-db – HTTP API

Serves the CSV databases in /data as a JSON REST API.

Endpoints
---------
GET  /                          Redirect to interactive docs
GET  /health                    Liveness check
GET  /api/v1/databases          List available databases with row counts
GET  /api/v1/databases/{name}   Return all rows from a named database
GET  /api/v1/aircraft           Search / filter across the main database
GET  /api/v1/aircraft/{icao}    Fetch a single aircraft record by ICAO hex
GET  /api/v1/categories         List all known aircraft categories

Query parameters for /api/v1/aircraft
--------------------------------------
icao         – partial or full ICAO hex (case-insensitive)
registration – partial match on $Registration
operator     – partial match on $Operator
type         – partial match on $Type
icao_type    – exact match on $ICAO Type
cmpg         – exact match on #CMPG  (Civ / Mil / Pol / Gov)
category     – exact match on Category
tag          – substring match across Tag 1 / Tag 2 / Tag 3
limit        – max rows returned (default 100, max 1000)
offset       – pagination offset (default 0)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import RedirectResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(os.environ.get("DATA_DIR", Path(__file__).parent.parent / "data"))

# Databases that can be served via /api/v1/databases/{name}
_DB_STEMS: dict[str, str] = {
    "main": "aircraft-taxonomy-db.csv",
    "pia": "aircraft-taxonomy-pia.csv",
    "civ": "aircraft-taxonomy-civ.csv",
    "mil": "aircraft-taxonomy-mil.csv",
    "pol": "aircraft-taxonomy-pol.csv",
    "gov": "aircraft-taxonomy-gov.csv",
    "wip": "aircraft-taxonomy-wip.csv",
}

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _clean_col(name: str) -> str:
    """Strip leading $# sigils from a column name to produce a clean key."""
    return name.lstrip("$#")


def _load_csv(filename: str) -> pd.DataFrame:
    path = DATA_DIR / filename
    if not path.is_file():
        return pd.DataFrame()
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    # Rename columns: strip sigils so callers use clean names
    df.columns = [_clean_col(c) for c in df.columns]
    return df


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return df.where(df != "", other=None).to_dict(orient="records")


# Load the main database once at startup; other databases are loaded on demand.
_main_df: pd.DataFrame = pd.DataFrame()


def _get_main_df() -> pd.DataFrame:
    global _main_df  # noqa: PLW0603
    if _main_df.empty:
        _main_df = _load_csv(_DB_STEMS["main"])
    return _main_df


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="aircraft-taxonomy-db API",
    description=(
        "REST API for the aircraft-taxonomy aircraft database. "
        "Returns JSON representations of CSV data files stored in /data."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect browser requests to the interactive Swagger docs."""
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe – always returns 200 OK when the service is running."""
    return {"status": "ok"}


@app.get("/api/v1/databases", tags=["databases"])
def list_databases() -> list[dict[str, Any]]:
    """Return all available databases with their file names and row counts."""
    result = []
    for name, filename in _DB_STEMS.items():
        path = DATA_DIR / filename
        if not path.is_file():
            continue
        df = _load_csv(filename)
        result.append(
            {
                "name": name,
                "filename": filename,
                "rows": len(df),
                "columns": list(df.columns),
            }
        )
    return result


@app.get("/api/v1/databases/{db_name}", tags=["databases"])
def get_database(
    db_name: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Return rows from a named database (main, civ, mil, pol, gov, pia, wip)."""
    if db_name not in _DB_STEMS:
        raise HTTPException(
            status_code=404,
            detail=f"Database '{db_name}' not found. "
            f"Available: {sorted(_DB_STEMS.keys())}",
        )
    df = _load_csv(_DB_STEMS[db_name])
    if df.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Database file for '{db_name}' does not exist on disk.",
        )
    total = len(df)
    page = df.iloc[offset : offset + limit]
    return {
        "database": db_name,
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": _df_to_records(page),
    }


@app.get("/api/v1/aircraft", tags=["aircraft"])
def search_aircraft(
    icao: str | None = Query(default=None, description="Partial ICAO hex (case-insensitive)"),
    registration: str | None = Query(default=None, description="Partial registration"),
    operator: str | None = Query(default=None, description="Partial operator name"),
    aircraft_type: str | None = Query(default=None, alias="type", description="Partial aircraft type"),
    icao_type: str | None = Query(default=None, description="Exact ICAO type code"),
    cmpg: str | None = Query(default=None, description="Civ | Mil | Pol | Gov"),
    category: str | None = Query(default=None, description="Exact category name"),
    tag: str | None = Query(default=None, description="Substring search across Tag 1/2/3"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Search and filter the main aircraft database.

    All text filters are case-insensitive.  Multiple filters are AND-combined.
    """
    df = _get_main_df()

    if df.empty:
        return {"total": 0, "offset": offset, "limit": limit, "rows": []}

    if icao:
        df = df[df["ICAO"].str.contains(icao, case=False, na=False, regex=False)]
    if registration:
        df = df[df["Registration"].str.contains(registration, case=False, na=False, regex=False)]
    if operator:
        df = df[df["Operator"].str.contains(operator, case=False, na=False, regex=False)]
    if aircraft_type:
        df = df[df["Type"].str.contains(aircraft_type, case=False, na=False, regex=False)]
    if icao_type:
        df = df[df["ICAO Type"].str.upper() == icao_type.upper()]
    if cmpg:
        df = df[df["CMPG"].str.upper() == cmpg.upper()]
    if category:
        df = df[df["Category"].str.upper() == category.upper()]
    if tag:
        tag_mask = (
            df["Tag 1"].str.contains(tag, case=False, na=False, regex=False)
            | df["Tag 2"].str.contains(tag, case=False, na=False, regex=False)
            | df["Tag 3"].str.contains(tag, case=False, na=False, regex=False)
        )
        df = df[tag_mask]

    total = len(df)
    page = df.iloc[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "rows": _df_to_records(page),
    }


@app.get("/api/v1/aircraft/{icao}", tags=["aircraft"])
def get_aircraft(icao: str) -> dict[str, Any]:
    """Return a single aircraft record by its exact ICAO 24-bit hex address."""
    df = _get_main_df()
    if df.empty:
        raise HTTPException(status_code=503, detail="Main database not available.")
    match = df[df["ICAO"].str.upper() == icao.upper()]
    if match.empty:
        raise HTTPException(
            status_code=404, detail=f"No aircraft found with ICAO hex '{icao.upper()}'."
        )
    # Return first match (ICAO hex should be unique, but handle duplicates gracefully)
    return _df_to_records(match)[0]


@app.get("/api/v1/categories", tags=["categories"])
def list_categories() -> list[str]:
    """Return all distinct aircraft category names present in the main database."""
    df = _get_main_df()
    if df.empty or "Category" not in df.columns:
        return []
    return sorted(df["Category"].dropna().unique().tolist())
