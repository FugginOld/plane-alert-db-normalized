# Plane Alert DB – HTTP API

The built-in HTTP API exposes supported CSV-backed databases from `data/` as a
JSON REST API, making them accessible to third-party tools, dashboards, and
scripts without having to parse CSV files directly.

---

## Table of Contents

- [Quick start](#quick-start)
- [Base URL and versioning](#base-url-and-versioning)
- [Authentication](#authentication)
- [Endpoints](#endpoints)
  - [GET /health](#get-health)
  - [GET /api/v1/databases](#get-apiv1databases)
  - [GET /api/v1/databases/{name}](#get-apiv1databasesname)
  - [GET /api/v1/aircraft](#get-apiv1aircraft)
  - [GET /api/v1/aircraft/{icao}](#get-apiv1aircrafticao)
  - [GET /api/v1/categories](#get-apiv1categories)
- [Pagination](#pagination)
- [Running standalone (without Docker Compose)](#running-standalone-without-docker-compose)

---

## Quick start

```bash
# Clone the repo (if you haven't already)
git clone https://github.com/FugginOld/aircraft-taxonomy-db.git
cd aircraft-taxonomy-db

# Start the API service
docker compose up -d api

# Open the interactive Swagger docs in your browser
open http://localhost:8000/docs
```

The service binds to **port 8000** by default.  Set the `API_PORT` environment
variable (or edit `docker-compose.yml`) to use a different port:

```bash
API_PORT=9000 docker compose up -d api
```

---

## Base URL and versioning

All endpoints are prefixed with `/api/v1/`.

| Base URL | Description |
|---|---|
| `http://localhost:8000/api/v1/` | Local development / self-hosted |
| `http://localhost:8000/docs` | Interactive Swagger UI |
| `http://localhost:8000/redoc` | ReDoc documentation |

---

## Authentication

No authentication is required.  The API is read-only.

---

## Endpoints

### GET /health

Liveness probe.  Returns `200 OK` when the service is running.

```
GET /health
```

**Response**

```json
{"status": "ok"}
```

---

### GET /api/v1/databases

List all available databases with their file names and row counts.

```
GET /api/v1/databases
```

**Response** (array)

```json
[
  {
    "name": "main",
    "filename": "plane-alert-db.csv",
    "rows": 15182,
    "columns": ["ICAO", "Registration", "Operator", "Type", "ICAO Type",
                "CMPG", "Tag 1", "Tag 2", "Tag 3", "Category"]
  },
  ...
]
```

Available database names: `main`, `civ`, `mil`, `pol`, `gov`, `pia`, `wip`.

---

### GET /api/v1/databases/{name}

Return rows from a named database.

```
GET /api/v1/databases/mil?limit=50&offset=0
```

**Path parameters**

| Parameter | Type   | Description |
|-----------|--------|-------------|
| `name`    | string | One of `main`, `civ`, `mil`, `pol`, `gov`, `pia`, `wip` |

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit`   | int  | `100`   | Max rows (1–1000) |
| `offset`  | int  | `0`     | Pagination offset |

**Response**

```json
{
  "database": "mil",
  "total": 8654,
  "offset": 0,
  "limit": 50,
  "rows": [
    {
      "ICAO": "000004",
      "Registration": "FAC1282",
      "Operator": "Colombian Aerospace Force",
      "Type": "CASA C-295 M",
      "ICAO Type": "C295",
      "CMPG": "Mil",
      "Tag 1": "Tactical Transport",
      "Tag 2": "Medium Lift",
      "Tag 3": "Twin Turboprop",
      "Category": "Tactical Airlift"
    },
    ...
  ]
}
```

---

### GET /api/v1/aircraft

Search and filter the main aircraft database.  All text filters are
case-insensitive; multiple filters are AND-combined.

```
GET /api/v1/aircraft?category=Tanker&cmpg=Mil&limit=20
```

**Query parameters**

| Parameter      | Type   | Default | Description |
|----------------|--------|---------|-------------|
| `icao`         | string | —       | Partial ICAO hex match |
| `registration` | string | —       | Partial registration match |
| `operator`     | string | —       | Partial operator name match |
| `type`         | string | —       | Partial aircraft type match |
| `icao_type`    | string | —       | Exact ICAO type code |
| `cmpg`         | string | —       | Exact group: `Civ`, `Mil`, `Pol`, or `Gov` |
| `category`     | string | —       | Exact category name (see `/api/v1/categories`) |
| `tag`          | string | —       | Substring match across Tag 1, Tag 2, and Tag 3 |
| `limit`        | int    | `100`   | Max rows (1–1000) |
| `offset`       | int    | `0`     | Pagination offset |

**Examples**

```bash
# All KC-135 tankers
curl "http://localhost:8000/api/v1/aircraft?icao_type=K35R"

# All aircraft operated by the RAF
curl "http://localhost:8000/api/v1/aircraft?operator=Royal+Air+Force"

# All UAV aircraft (any tag containing "UAV")
curl "http://localhost:8000/api/v1/aircraft?category=UAV+-+Recon"

# ICAO hex lookup (partial)
curl "http://localhost:8000/api/v1/aircraft?icao=AE"
```

**Response**

```json
{
  "total": 42,
  "offset": 0,
  "limit": 100,
  "rows": [ { ... }, ... ]
}
```

---

### GET /api/v1/aircraft/{icao}

Fetch a single aircraft record by its exact ICAO 24-bit hex address.

```
GET /api/v1/aircraft/AE01CE
```

**Path parameters**

| Parameter | Type   | Description |
|-----------|--------|-------------|
| `icao`    | string | Exact ICAO hex (case-insensitive, e.g. `AE01CE`) |

**Response**

```json
{
  "ICAO": "AE01CE",
  "Registration": "12-3456",
  "Operator": "United States Air Force",
  "Type": "Boeing KC-135R Stratotanker",
  "ICAO Type": "K35R",
  "CMPG": "Mil",
  "Tag 1": "Air Refuelling",
  "Tag 2": "Long Range",
  "Tag 3": "Quad Engine",
  "Category": "Tanker"
}
```

Returns `404` if not found.

---

### GET /api/v1/categories

List all distinct aircraft category names present in the main database.

```
GET /api/v1/categories
```

**Response** (sorted array of strings)

```json
[
  "AEW&C",
  "Attack / Strike",
  "Business Jet",
  "Cargo Freighter",
  ...
]
```

---

## Pagination

All list endpoints support `limit` and `offset` query parameters.

```bash
# First page
curl "http://localhost:8000/api/v1/aircraft?limit=50&offset=0"

# Second page
curl "http://localhost:8000/api/v1/aircraft?limit=50&offset=50"
```

The response always includes a `total` field showing the number of rows that
matched the query (before pagination), so clients can calculate the number of
pages: `pages = ceil(total / limit)`.

---

## Running standalone (without Docker Compose)

```bash
cd api
pip install -r requirements.txt
DATA_DIR=../data uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
