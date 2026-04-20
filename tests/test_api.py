"""Tests for api/main.py endpoints.

Runs against an in-memory patched dataset so no real CSV files are required.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

# Ensure the api/ directory is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "api"))

import main as api_main  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE_ROWS = [
    {
        "$ICAO": "AE1234",
        "$Registration": "N12345",
        "$Operator": "US Air Force",
        "$Type": "C-130 Hercules",
        "$ICAO Type": "C130",
        "#CMPG": "Mil",
        "Category": "Tactical Airlift",
        "$Tag 1": "Tactical Transport",
        "$#Tag 2": "Heavy Lift",
        "$#Tag 3": "Turboprop",
    },
    {
        "$ICAO": "BF5678",
        "$Registration": "G-ABCD",
        "$Operator": "British Airways",
        "$Type": "Boeing 737-800",
        "$ICAO Type": "B738",
        "#CMPG": "Civ",
        "Category": "Passenger - Narrowbody",
        "$Tag 1": "",
        "$#Tag 2": "",
        "$#Tag 3": "Jet",
    },
    {
        "$ICAO": "CF9012",
        "$Registration": "C-FXXX",
        "$Operator": "RCMP",
        "$Type": "Bell 412",
        "$ICAO Type": "B412",
        "#CMPG": "Pol",
        "Category": "Helicopter - Utility",
        "$Tag 1": "Utility",
        "$#Tag 2": "",
        "$#Tag 3": "Rotorcraft",
    },
]


@pytest.fixture(autouse=True)
def patch_data(tmp_path):
    """Write a minimal CSV to a temp dir and point the API at it."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    df = pd.DataFrame(_SAMPLE_ROWS)
    csv_path = data_dir / "aircraft-taxonomy-db.csv"
    df.to_csv(csv_path, index=False)

    # Reset the cached main DataFrame before each test
    api_main._main_df = pd.DataFrame()

    with patch.object(api_main, "DATA_DIR", data_dir):
        yield


@pytest.fixture()
def client():
    return TestClient(api_main.app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /api/v1/databases
# ---------------------------------------------------------------------------

def test_list_databases_returns_main(client):
    r = client.get("/api/v1/databases")
    assert r.status_code == 200
    names = [db["name"] for db in r.json()]
    assert "main" in names


def test_get_database_main(client):
    r = client.get("/api/v1/databases/main")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["rows"]) == 3


def test_get_database_unknown_returns_404(client):
    r = client.get("/api/v1/databases/nonexistent")
    assert r.status_code == 404


def test_get_database_pagination(client):
    r = client.get("/api/v1/databases/main?limit=2&offset=0")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert len(body["rows"]) == 2

    r2 = client.get("/api/v1/databases/main?limit=2&offset=2")
    assert r2.json()["rows"][0]["ICAO"] == "CF9012"


# ---------------------------------------------------------------------------
# /api/v1/aircraft  (search)
# ---------------------------------------------------------------------------

def test_search_no_filters_returns_all(client):
    r = client.get("/api/v1/aircraft")
    assert r.status_code == 200
    assert r.json()["total"] == 3


def test_search_by_icao_partial(client):
    r = client.get("/api/v1/aircraft?icao=AE")
    assert r.json()["total"] == 1
    assert r.json()["rows"][0]["ICAO"] == "AE1234"


def test_search_by_icao_case_insensitive(client):
    r = client.get("/api/v1/aircraft?icao=ae1234")
    assert r.json()["total"] == 1


def test_search_by_operator(client):
    r = client.get("/api/v1/aircraft?operator=british")
    assert r.json()["total"] == 1
    assert r.json()["rows"][0]["Registration"] == "G-ABCD"


def test_search_by_cmpg(client):
    r = client.get("/api/v1/aircraft?cmpg=Mil")
    assert r.json()["total"] == 1
    assert r.json()["rows"][0]["ICAO"] == "AE1234"


def test_search_by_cmpg_case_insensitive(client):
    r = client.get("/api/v1/aircraft?cmpg=mil")
    assert r.json()["total"] == 1


def test_search_by_category(client):
    r = client.get("/api/v1/aircraft?category=Tactical+Airlift")
    assert r.json()["total"] == 1


def test_search_by_tag(client):
    r = client.get("/api/v1/aircraft?tag=Rotorcraft")
    assert r.json()["total"] == 1
    assert r.json()["rows"][0]["ICAO"] == "CF9012"


def test_search_by_icao_type_exact(client):
    r = client.get("/api/v1/aircraft?icao_type=B738")
    assert r.json()["total"] == 1


def test_search_combined_filters(client):
    r = client.get("/api/v1/aircraft?cmpg=Civ&type=Boeing")
    assert r.json()["total"] == 1
    assert r.json()["rows"][0]["ICAO"] == "BF5678"


def test_search_no_match_returns_empty(client):
    r = client.get("/api/v1/aircraft?operator=doesnotexist")
    assert r.json()["total"] == 0
    assert r.json()["rows"] == []


def test_search_empty_string_in_response_is_none(client):
    r = client.get("/api/v1/aircraft?icao=BF5678")
    rows = r.json()["rows"]
    assert rows[0]["Tag 1"] is None


# ---------------------------------------------------------------------------
# /api/v1/aircraft/{icao}
# ---------------------------------------------------------------------------

def test_get_aircraft_by_icao(client):
    r = client.get("/api/v1/aircraft/AE1234")
    assert r.status_code == 200
    assert r.json()["ICAO"] == "AE1234"


def test_get_aircraft_by_icao_case_insensitive(client):
    r = client.get("/api/v1/aircraft/ae1234")
    assert r.status_code == 200


def test_get_aircraft_not_found(client):
    r = client.get("/api/v1/aircraft/000000")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# /api/v1/categories
# ---------------------------------------------------------------------------

def test_list_categories(client):
    r = client.get("/api/v1/categories")
    assert r.status_code == 200
    cats = r.json()
    assert "Tactical Airlift" in cats
    assert "Passenger - Narrowbody" in cats
    assert cats == sorted(cats)


# ---------------------------------------------------------------------------
# API key auth
# ---------------------------------------------------------------------------

def test_auth_disabled_by_default(client):
    r = client.get("/api/v1/aircraft")
    assert r.status_code == 200


def test_auth_required_when_api_key_set(client):
    with patch.object(api_main, "_API_KEY", "secret"):
        r = client.get("/api/v1/aircraft")
        assert r.status_code == 401


def test_auth_passes_with_correct_key(client):
    with patch.object(api_main, "_API_KEY", "secret"):
        r = client.get("/api/v1/aircraft", headers={"X-API-Key": "secret"})
        assert r.status_code == 200


def test_auth_open_paths_bypass_key_check(client):
    with patch.object(api_main, "_API_KEY", "secret"):
        assert client.get("/health").status_code == 200
        assert client.get("/docs").status_code == 200
