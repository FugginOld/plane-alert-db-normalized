# Migration Guide: Personality/Group Categories → Aviation Taxonomy

## What changed and why

This repository has been restructured from a personality/group-category classification system to a structured **aviation-taxonomy** system. The old system used creative, humour-driven category names (e.g. *Zoomies*, *Toy Soldiers*, *Flying Doctors*, *Jump Johnny Jump*) that described *who* operated an aircraft or what the maintainer found interesting about it. While fun, those names made it hard to filter the database programmatically or query it by aircraft capability.

The new system classifies every aircraft by **what it is** — its role, mission, and configuration — regardless of who operates it.

---

## Category mapping reference

The table below shows how the old personality categories map to the new taxonomy. Many old categories spanned several aircraft types; the mapping is therefore approximate.

| Old Category | New Category (most common match) |
|---|---|
| USAF | *(varies by aircraft type — e.g. Fighter / Interceptor, Tanker, Strategic Airlift, Trainer, ISR / Surveillance)* |
| Other Air Forces | *(varies by aircraft type)* |
| RAF | *(varies by aircraft type)* |
| GAF | *(varies by aircraft type)* |
| Toy Soldiers | *(varies — Tactical Airlift, Helicopter - Transport, Trainer, etc.)* |
| Gunship | Attack / Strike |
| Zoomies | Fighter / Interceptor |
| Oxcart | ISR / Surveillance |
| Dogs with Jobs | ISR / Surveillance or Special Mission |
| Hired Gun | Special Mission |
| Special Forces | Special Mission |
| Flying Doctors | Helicopter - Utility or Utility |
| Aerial Firefighter | Special Mission |
| Ptolemy would be proud | Utility or ISR / Surveillance |
| United States Navy | *(varies — Fighter / Interceptor, Maritime Patrol, Helicopter - Maritime, etc.)* |
| United States Marine Corps | *(varies — Attack / Strike, Helicopter - Transport, etc.)* |
| Royal Navy Fleet Air Arm | Helicopter - Maritime |
| Other Navies | *(varies)* |
| Coastguard | Maritime Patrol or Helicopter - Maritime |
| Bizjets | Business Jet |
| Climate Crisis | Business Jet or Passenger - Widebody |
| Oligarch | Business Jet |
| Radiohead | Special Mission |
| Joe Cool | *(varies)* |
| Distinctive | Special Mission |
| Historic | Special Mission or Trainer |
| Big Hello | Helicopter - Transport |
| Army Air Corps | Helicopter - Utility |
| Aerobatic Teams | Trainer |
| Watch Me Fly | Trainer |
| Jump Johnny Jump | Trainer |
| You came here in that thing? | Utility |
| Gas Bags | Utility |
| UAV | UAV - Recon or UAV - Combat or UAV - Utility |
| Governments | *(varies)* |
| Quango | *(varies)* |
| Police Forces | Helicopter - Utility |
| UK National Police Air Service | Helicopter - Utility |
| CAP | Utility |
| Dictator Alert | Passenger - Widebody or Business Jet |
| Head of State | Passenger - Widebody or Business Jet |
| As Seen on TV | Business Jet |
| Football | Business Jet |
| Jesus he Knows me | Utility |
| Nuclear | Special Mission |
| Ukraine | *(varies by aircraft type)* |
| Da Comrade | *(varies by aircraft type)* |
| Vanity Plate | *(varies — kept in the database but Category set by aircraft type)* |
| Perfectly Serviceable Aircraft | Utility |
| Don't you know who I am? | Business Jet |
| Royal Aircraft | Business Jet or Passenger - Widebody |
| PIA | *(kept in plane-alert-pia.csv separately)* |

---

## Tag structure

Each aircraft carries up to three structured tags. The old tag fields carried free-text narrative phrases (*"Marching Powder"*, *"Through Hardships To The Stars"*, etc.). Those are replaced with enumerated values:

| Field | Old style | New style | Allowed values |
|---|---|---|---|
| `$Tag 1` | Narrative / callout phrase | Primary mission role | `Tactical Transport`, `Strategic Transport`, `Maritime Patrol`, `ISR`, `Early Warning`, `Air Superiority`, `Strike`, `Close Air Support`, `Refueling`, `Training`, `Utility`, `Electronic Warfare` |
| `$#Tag 2` | Narrative / callout phrase | Capability or configuration | `STOL`, `Long Range`, `Short Runway`, `Heavy Lift`, `Medium Lift`, `Multi-Role`, `All-Weather`, `High Endurance`, `Aerial Refueling`, `Carrier Capable`, `Amphibious`, `Basic Trainer`, `Light Lift`, `Low Altitude` |
| `$#Tag 3` | Narrative / callout phrase | Propulsion or airframe | `Twin Turboprop`, `Turboprop`, `Twin Engine`, `Quad Engine`, `Jet`, `High Wing`, `Low Wing`, `Rear Ramp`, `Side Door`, `Pressurized`, `Sensor Suite`, `Modular Cabin`, `Single Engine`, `Rotorcraft` |

---

## What did NOT change

- **`#CMPG`** — The operator-type split (`Mil` / `Civ` / `Gov` / `Pol`) is unchanged. It drives the derivative files (`plane-alert-mil.csv`, `plane-alert-civ.csv`, `plane-alert-gov.csv`, `plane-alert-pol.csv`) and is orthogonal to the taxonomy.
- **`$ICAO`**, **`$Registration`**, **`$Operator`**, **`$Type`**, **`$ICAO Type`** — All identifier columns are unchanged.

---

## Impact on downstream consumers

If you use the `Category` field in your configuration rules, you will need to update your filter values to use the new taxonomy names. The 53 old category names are no longer present in the database.

If you use the `#CMPG` field or the derivative files (`plane-alert-mil.csv`, etc.), no changes are needed.

---

## Running the normalizer

To apply or extend the taxonomy mapping yourself:

```bash
pip install -r scripts/requirements.txt

python scripts/normalize_aircraft_v5.py data/plane-alert-db.csv \
    --lookup taxonomy/aircraft_type_lookup.csv \
    --aliases taxonomy/aircraft_type_aliases.csv

# For a production-ready output without diagnostic columns:
python scripts/normalize_aircraft_v5.py data/plane-alert-db.csv \
    --lookup taxonomy/aircraft_type_lookup.csv \
    --aliases taxonomy/aircraft_type_aliases.csv \
    --no-audit-cols
```

- Review `data/plane-alert-db_review.csv` for any rows the normalizer could not classify.
- Add missing ICAO types to `taxonomy/aircraft_type_lookup.csv` and re-run.
- Add free-text type-name variants to `taxonomy/aircraft_type_aliases.csv` and re-run.

See `scripts/README.md` for full documentation.
