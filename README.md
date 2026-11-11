# FoodBridge

**A food rescue platform for Philadelphia.** FoodBridge connects organizations that have surplus food (restaurants, grocers, bakeries, cafeterias, caterers, farms, distributors) with the pantries, shelters and meal sites that need it. Donors post surplus food, recipients post requests, and allocations link the two while making sure no donation or request is over-allocated. The analytics pages show supply vs. demand, food lost to expiry, and geographic gaps in coverage.

CIS 5500 – Database and Information Systems, Fall 2026 · **Group 25**

| Member | Role |
|---|---|
| Sumit Pradeep Kolpe | Database design, SQL queries, optimization, integration |
| Urav Dalal | Data acquisition, cleaning, synthetic data |
| Jigar Shah | Backend (Node.js / Express API) |
| Rushabh Maru | Frontend (React) |

**Stack:** PostgreSQL on AWS RDS · Python (pandas) data pipeline · Node.js / Express · React

---

## Milestone status

| Milestone | Status | Where |
|---|---|---|
| M1 – Proposal | Done | [`docs/milestones/M1_Proposal.pdf`](docs/milestones/M1_Proposal.pdf) |
| M2 – Detailed outline (schema, ER diagram, DDL) | Done | [`docs/milestones/M2_Detailed_Project_Outline.pdf`](docs/milestones/M2_Detailed_Project_Outline.pdf) |
| M3 – Database populated on RDS + SQL queries | Done | [`docs/milestones/M3_Database_and_Queries.pdf`](docs/milestones/M3_Database_and_Queries.pdf), [`sql/queries.sql`](sql/queries.sql) |
| M4 – API specification + mentor check-in | Next | `server/` (coming) |
| M5 – Final report, code, demo video | Upcoming | `client/`, `server/` (coming) |

## Repository layout

| Path | Contents |
|---|---|
| `data/raw/philly_free_food_sites_raw_2026-11-10.csv` | Frozen export of the City of Philadelphia **Free Food & Meal Sites** dataset (real data, 404 rows) |
| `data/raw/synthetic/` | Raw synthetic files as if exported from an intake system, including simulated noise for the cleaning step to handle |
| `data/interim/` | Intermediate outputs: cleaned Philly sites, entity-resolution maps (`philly_er_map.csv`, `org_key_map.csv`), `organization_meta.csv` (provenance, lat/lon) |
| `data/processed/` | **Final CSVs, one per table, columns in DDL order**: these are what is loaded into PostgreSQL |
| `scripts/` | Python pipeline: steps 01–05, `run_pipeline.py`, `common.py` (config + entity resolution), `06_make_insert_scripts.py` |
| `sql/schema.sql` | PostgreSQL DDL (approved in M2) |
| `sql/load_data.sql` | Bulk load with `psql \copy`, sequence reset, row counts |
| `sql/verify_load.sql` | Post-load row counts and business-rule checks |
| `sql/create_guest_user.sql` | Read-only `fb_guest` role for TAs (password set at deploy time, never committed) |
| `sql/queries.sql` | **The 12 Milestone 3 queries** (6 simple, 6 complex) |
| `sql/optimization_notes.md` | Baseline timings and first optimization findings |
| `reports/` | `philly_eda.md` (EDA + entity resolution log), `cleaning_report.md`, `data_summary.md` (statistics + 41 validation checks) |
| `docs/milestones/` | Submitted milestone documents (M3 also as LaTeX source) |
| `server/`, `client/` | Express API and React app (added in M4/M5) |

## Reproduce the database

```bash
pip install -r requirements.txt
python scripts/run_pipeline.py          # rebuilds data/ and reports/ (~20 s, deterministic, seed 20261019)

psql -h <rds-endpoint> -U <user> -d foodbridge -f sql/schema.sql
psql -h <rds-endpoint> -U <user> -d foodbridge -f sql/load_data.sql      # run from the repo root
psql -h <rds-endpoint> -U <user> -d foodbridge -f sql/verify_load.sql
```

**Without psql** (e.g. DataGrip only): run `python scripts/06_make_insert_scripts.py .`. This writes batched INSERT files to `sql/inserts/` (not committed, ~46 MB). Run `00_reset_tables.sql` through `06_finish.sql` in order.

## Data

**1. Philadelphia Free Food and Meal Sites (real).** Source: OpenDataPhilly / City of Philadelphia ArcGIS FeatureServer `free_meal_sites`, exported 2026-11-10. The file has 404 rows and 51 attributes, plus lon/lat.

**2. Synthetic operational data.** The public data contains no donations, requests or allocations, so these are simulated. This covers the donor organizations, the extra recipient organizations, donations, requests and allocations. Every synthetic record is generated, not real. Phone numbers use the fictional 555 exchange and email addresses use `.example.org`.

### Pipeline

| Step | Script | What it does |
|---|---|---|
| 01 | `01_clean_philly_sites.py` | **EDA and cleaning:** standardizes ZIP codes and status values, and splits the field that mixes phone numbers and emails. **Entity resolution:** the city lists one row per *program*, so the same church appears several times with spelling variants like "Ave" vs "Ave.". Records are blocked on normalized address and matched on name similarity, merging 404 rows into 371 organizations. ZIP conflicts are resolved using Philadelphia's N/S street numbering. Sites that only offer Public Benefits are removed, leaving **346 recipient sites**. |
| 02 | `02_generate_synthetic_raw.py` | Generates 654 synthetic organizations (499 donors across 9 business types, 120 recipients, 35 that both donate and receive), 25 food categories, 150,000 donations and 120,000 requests. Volumes include growth, seasonality and weekday patterns, with realistic category mixes and shelf lives. **Simulated source noise** is added for the cleaning step: 5% duplicate registrations, label and format variants, invalid rows, and double submissions. Ground truth for the duplicates is saved. |
| 03 | `03_clean_integrate.py` | Resolves duplicate registrations with the same ER routine (precision 1.00, recall 1.00 against ground truth). Standardizes values, parses mixed formats, and removes invalid rows and double submissions. Maps every source key to `organization_id`. |
| 04 | `04_generate_allocations.py` | Event-driven, two-sided matching per food category produces **198,415 allocations**. Business rules are enforced: allocations never exceed a donation's quantity or a request's requested quantity, categories match, and timestamps are in order. Statuses are then derived relative to the snapshot time. |
| 05 | `05_validate_and_summarize.py` | Runs 41 checks (primary keys, NOT NULL, CHECK constraints, foreign keys, business rules) and writes summary statistics. The pipeline fails if any check fails. |

### Final tables

| Table | Rows |
|---|---:|
| Organization | 1,000 (ids 1–346 real Philly sites, 347–1000 synthetic) |
| FoodCategory | 25 |
| FoodDonation | 150,000 |
| RecipientRequest | 120,000 |
| Allocation | 198,415 |

### Status rules

Statuses are computed relative to the snapshot time `AS_OF = 2026-11-10 12:00`.

- **FoodDonation:**
  - `fully_allocated`: active allocations equal the donated quantity.
  - `expired`: the pickup window closed with food left over.
  - `partially_allocated` or `available`: the pickup window is still open.
  - `cancelled`: withdrawn before being matched.
- **RecipientRequest:**
  - `fulfilled`: delivered servings are at least the requested quantity.
  - `partially_fulfilled`: some servings delivered or allocated, but fewer than requested.
  - `expired`: `needed_by` passed with nothing delivered.
  - `open`: nothing allocated yet and the deadline has not passed.
  - `cancelled`: withdrawn before being matched.
- **Allocation:** moves through `pending` → `confirmed` → `picked_up` → `delivered`, or ends as `cancelled`. Cancelled quantities do not count toward the quantity limits.

Queries and the app use the reference time `2026-11-10 12:00` (an `as_of` parameter) instead of `NOW()`, so that time-based features keep working on this snapshot.
