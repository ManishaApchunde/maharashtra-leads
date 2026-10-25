# Maharashtra Xerox / Print Shop Lead Database — Land Recorder Bot

A MySQL lead database of Xerox, photocopy, printing, cyber café, CSC, DTP and e-Seva
businesses across all 36 districts of Maharashtra, with cleaning, duplicate review, lead
scoring, government-office proximity, CSV/Excel import and export, and a React admin dashboard.

**Stack:** FastAPI · SQLAlchemy 2 · Alembic · Pydantic · MySQL 8 (PyMySQL, utf8mb4) · rapidfuzz · React + Vite · Recharts

```
maharashtra-leads/
├── docker-compose.yml          MySQL 8.4
├── backend/
│   ├── app/
│   │   ├── main.py             FastAPI app + CORS + optional API key
│   │   ├── config.py, database.py, deps.py
│   │   ├── models/             SQLAlchemy tables (geo.py, business.py)
│   │   ├── schemas/            Pydantic request/response models
│   │   ├── routes/             businesses, geo, duplicates, imports, exports,
│   │   │                       gov_offices, analytics, collection, admin
│   │   ├── services/           cleaning, dedup, ingest, scoring, proximity,
│   │   │                       query (shared filters), places_api, filereader
│   │   └── utils/              phone, text, geo, sql (MySQL helpers), maharashtra (districts, categories, keywords)
│   ├── alembic/versions/0001_initial_schema.py
│   ├── tests/test_cleaning.py
│   ├── requirements.txt
│   └── .env.example
├── frontend/                   React admin (8 pages)
└── sample_data/                TEST_DATA files + templates
```

---

## Quick start (step by step)

You need: **Python 3.11+**, **Node 18+**, and either **Docker** or a local **MySQL 8.0.13+** (8.4 LTS recommended).

### Step 1 — MySQL

```bash
docker compose up -d
docker compose ps          # STATUS should say "healthy" (first start takes ~20 s)
```

No Docker? Create the database yourself (MySQL Workbench or `mysql -u root -p`):

```sql
CREATE DATABASE maharashtra_leads CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'leads'@'localhost' IDENTIFIED BY 'leads';
GRANT ALL PRIVILEGES ON maharashtra_leads.* TO 'leads'@'localhost';
FLUSH PRIVILEGES;
```

Use your own user/password if you like — just put them in `DATABASE_URL` in `backend/.env`:
`mysql+pymysql://USER:PASSWORD@HOST:3306/maharashtra_leads?charset=utf8mb4`
(URL-encode special characters in the password, e.g. `@` → `%40`).

> **`utf8mb4` matters.** It is what lets Marathi/Devanagari names and addresses save correctly, and the
> `_ci` collation makes filters case-insensitive (`pune` = `Pune`).

### Step 2–3 — Backend, models and migrations

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # Windows: copy .env.example .env
alembic upgrade head
```

Expected output ends with:

```
INFO  [alembic.runtime.migration] Running upgrade  -> 0001, initial schema
```

The migration creates all tables (InnoDB, utf8mb4) and indexes and seeds the 36 districts,
13 categories and the default data sources. **No businesses are seeded.** No stored functions or
plugins are created, so an ordinary (non-root) MySQL user is enough.

> `Access denied` → check user/password/host in `DATABASE_URL`.
> `RuntimeError: 'cryptography' package is required` → `pip install cryptography` (MySQL 8 login).
> `Unknown database` → run the `CREATE DATABASE` statement above first.

### Step 4 — Start the API

```bash
uvicorn app.main:app --reload --port 8000
```

Test it:

```bash
curl http://localhost:8000/health
# {"status":"ok","database":"connected"}
curl http://localhost:8000/districts       # 36 districts
```

Interactive API docs: **http://localhost:8000/docs**

### Step 5–7 — Import, cleaning, duplicate detection (try with TEST_DATA)

```bash
cd ../sample_data
curl -F file=@TEST_DATA_government_offices.csv -F source=TEST_DATA http://localhost:8000/import/government-offices
curl -F file=@TEST_DATA_businesses.csv -F source=TEST_DATA http://localhost:8000/import/csv
```

Expected summary for the business file:

```json
{"status":"completed","total":10,"new":6,"duplicates":1,"possible_duplicates":1,"invalid":2, ...}
```

What happened to the 10 rows:

| Row | Result | Why |
|---|---|---|
| Om Xerox Center | new | — |
| Om Xerox Centre (phone `09000000001`, district "Poona") | **duplicate** (merged) | same normalised phone + same core name "om" |
| OM XEROX (no phone, 24 m away) | **possible duplicate** | very similar name, 24 m apart, same PIN → goes to Duplicate review |
| "90000 00002 / 90000 00003" | new | split into phone + alternate phone |
| Ahmednagar | new | district renamed to official "Ahilyanagar" |
| Phone `12345`, no address | **invalid** | no valid phone, address or coordinates |
| Blank shop name | **invalid** | missing shop_name |
| PIN 560001 | new, flagged | `pincode_outside_maharashtra` |
| District "Mumbai" | new, flagged | `unrecognized_district` (could be City or Suburban — not guessed) |

TEST_DATA rows are hidden from lists, dashboard and exports unless you tick **Include TEST_DATA**.
Remove them any time: `curl -X DELETE http://localhost:8000/admin/test-data`.

Run the unit tests:

```bash
cd ../backend && pytest -q        # 11 passed
```

### Step 8 — Search / filter API

```bash
curl "http://localhost:8000/businesses?district=Pune&category=Xerox&has_whatsapp=true&min_score=40&lead_status=New&include_test_data=true"
curl "http://localhost:8000/businesses?q=9000000002&include_test_data=true"
```

### Step 9 — Admin dashboard

```bash
cd ../frontend
npm install
cp .env.example .env
npm run dev
```

Open **http://localhost:5173**. The sidebar shows "API connected" when the backend is reachable.

| Page | What it does |
|---|---|
| Dashboard | 14 headline numbers + charts by district/taluka/city, category, lead status, source, score band. Drill down Maharashtra → District → Taluka → City. |
| Businesses & leads | Search + combined filters, click a row for details, score breakdown, lead status/notes/follow-up, edit, manual add |
| Duplicate review | Side-by-side pairs: keep existing / keep newer / different shops |
| Import | CSV/Excel upload with summary and invalid-row list; government offices; taluka/village master data |
| Export | One-click presets + any filter → marketing-ready CSV |
| Data collection | Area + keyword search via Google Places API, and a log of every collection run |
| Government offices | Add/list offices, recalculate proximity and scores |
| Data quality | Missing/invalid phone, address, district, PIN, coordinates, duplicates, unverified, old records |

### Step 10 — CSV export

```bash
curl -OJ "http://localhost:8000/export/csv?district=Pune&category=Xerox"
curl -OJ "http://localhost:8000/export/csv?has_whatsapp=true"
curl -OJ "http://localhost:8000/export/csv?min_score=60&contacted=false"
curl -OJ "http://localhost:8000/export/csv?near_office_m=1000&office_type=Talathi%20Office"
```

Columns include normalised phone, `https://wa.me/91…` link, all categories, score + reasons,
lead status, follow-up date, nearest government office and distance. The file has a UTF-8 BOM
so Excel shows Marathi text correctly. Exports stream, so 100k+ rows are fine.

### Steps 11–12 — Lead score and government-office proximity

After adding offices (Import page or `POST /government-offices`), click **Recalculate proximity &
scores** or run `curl -X POST http://localhost:8000/government-offices/recompute-proximity`.

| Factor | Points |
|---|---|
| Xerox / photocopy business | +20 |
| Online / government document services (Online Services, E-Seva) | +20 |
| CSC | +15 |
| Printing / Digital printing / DTP | +10 |
| Valid phone | +10 |
| WhatsApp number | +10 |
| Within 1 km of a government office (+5 if within 2 km) | +10 |
| 20+ public reviews | +5 |

Capped at 100. **This is a marketing-priority checklist, not a statistical prediction.**
Change the points in `backend/app/services/scoring.py` (`RULES`), then call `POST /admin/rescore`.

### Step 13 — Authorised API collection (Google Places API)

1. Create a key for **Places API (New)** in Google Cloud and set `GOOGLE_PLACES_API_KEYS=KEY_1,KEY_2` (one line,
   comma-separated) in `backend/.env`. A rejected key (invalid / restricted / API or billing off) is skipped and the
   next key used; a used-up quota pauses the district job (status **Paused**) so you can resume it later.
2. Restart the API, open **Data collection**, choose District / Taluka / City + keyword, click **Run search**.

The collector uses only the official Text Search endpoint, at most 3 pages × 20 results per run,
with a pause between pages. Results outside Maharashtra are rejected. The district comes from
Google's address data where available; otherwise the searched district is used and the record is
flagged `district_from_search_area`. The taluka is only set if the address mentions it.

> ⚠ **Read Google's terms before relying on this for a permanent list.** Google Maps Platform
> terms restrict caching/storing most Places content long-term (place IDs may be stored). Every
> API row is tagged `source = "Google Places API"` with its `source_place_id`, so you can refresh
> or remove those rows. For a long-lived database, prefer data you have rights to keep: your own
> field collection, CSC/e-Seva lists you're permitted to use, partner lists, or licensed directories.

Nothing in this project scrapes Google Maps pages or works around CAPTCHAs, logins or rate limits.

#### Collect a whole district automatically

On **Data collection → Collect a whole district automatically**, pick a district (or *All 36 districts*)
and click **Collect all of …**. A background job then searches, for **every ticked keyword** (all 19 by default):

1. **Every taluka** of the district — all 358 Maharashtra talukas are built in (`app/utils/talukas.py`)
   and added to the `talukas` table on startup, plus the taluka's main town where its name differs (Baglan → Satana).
2. **Big-city areas** (Mumbai, Pune, Thane, Nagpur, Nashik…), because one search returns at most 60 places.
3. **Every village / town the database knows** for that district — re-read after step 1, so towns found
   in step 1 are searched too. To cover *every* village, import a village list first
   (`POST /import/geo`, columns `district,taluka,location,type`, e.g. from the Census village directory).
4. Optional **map-grid sweep**: the district's map box is split into 3–12 km cells and each cell is
   searched — this reaches villages that are not in the database.

Each search is saved as a normal collection run and goes through the same cleaning and duplicate
checks, so overlapping keywords just merge into existing rows. With **Skip areas already searched**
on, a stopped or interrupted job resumes where it left off. One job runs at a time; if Google returns
a quota/rate error the job waits and retries, and it stops on a bad key / billing error.

Cost: every page is one billable Text Search request. The panel shows the number of searches and the
maximum requests before you start (e.g. Akola with 19 keywords ≈ 133 taluka searches + villages).
Use **Core 10** keywords to roughly halve that. Don't run the backend with `--reload` during a long job —
a reload restarts the server and stops the job (re-run it with *skip* on).

API: `POST /collection/district-plan`, `POST /collection/district-jobs`, `GET /collection/district-jobs[/{id}]`,
`POST /collection/district-jobs/{id}/cancel`.

---

## How the important parts work

### Phone normalisation (`utils/phone.py`)

`+91 98765 43210`, `09876543210`, `919876543210`, `98765-43210` → `9876543210`.
Landlines keep STD code without the leading 0 (`020-2445 1234` → `2024451234`). Anything that isn't
10 digits is flagged `invalid_phone` and its `normalized_phone` stays empty. Multiple numbers in one
cell (`/`, `,`, `;`, `or`) are split into phone + alternate. WhatsApp is **never** assumed from the
phone column; it's filled only from a `whatsapp_number` column (or `whatsapp_same_as_phone = yes`).

### Cleaning (`services/cleaning.py`)

Trims and collapses whitespace, title-cases ALL-CAPS names, maps old district names
(Aurangabad → Chhatrapati Sambhajinagar, Ahmednagar → Ahilyanagar, Osmanabad → Dharashiv, Poona → Pune…),
strips "Taluka/Tal." suffixes, validates PIN codes (Maharashtra = 40xxxx–44xxxx), checks coordinates
fall inside Maharashtra, standardises categories from the category text **and** the shop name, and
records every problem in `quality_flags`. Missing values stay `NULL`; `contact_name` is never guessed.

### Duplicate detection (`services/dedup.py`)

Candidates are fetched by: same source place ID · same phone (any of phone/alternate/WhatsApp) ·
similar name in the same PIN or same district+city (scored in Python with `rapidfuzz`, since MySQL has
no trigram search) · anything within ~150 m.
Each candidate is scored:

| Signal | Points |
|---|---|
| Same phone | 60 |
| Name similarity ≥ 90 % / ≥ 80 % | 30 / 20 |
| Address similarity ≥ 85 % | 15 |
| ≤ 50 m / ≤ 150 m apart | 20 / 10 |
| Same PIN | 5 |

Name similarity compares the *distinctive* part of the name ("Om Xerox Centre" → "om"), so
"Om Xerox Center", "Om Xerox Centre" and "OM XEROX" match, but "Sai Xerox" and "Om Sai Xerox" don't.

* **Duplicate** (same place ID, or same phone + name ≥ 85 %): not inserted again; empty fields on the
  existing record are filled in. Nothing is overwritten.
* **Possible duplicate** (score ≥ 40 with a phone or name match): inserted with
  `duplicate_status = possible_duplicate` and queued for review.
* Confirming a duplicate **keeps both rows**; the duplicate is marked `confirmed_duplicate`, linked
  via `duplicate_of_id`, and hidden from lists/exports. Rejecting returns both to `unique`.

### Geography

36 districts are seeded. Talukas and cities/villages are created automatically as data is imported,
or bulk-loaded via **Import → Talukas & villages** (`sample_data/geo_template.csv`). Every business
stores both the text (`district`, `taluka`, `city`, `area`, `village`) and foreign keys
(`district_id`, `taluka_id`, `location_id`).

### Scale

Designed for hundreds of thousands of rows without schema changes: B-tree indexes on phone,
normalised phone, district, taluka, city, pincode, category, lead_status, verification_status,
duplicate_status, score; composite indexes (district+taluka+city, district+lead_status+score, lat+lng).
City/taluka lookups are case-insensitive through the `utf8mb4_unicode_ci` collation, so they use these
indexes directly. Distances are computed with the haversine formula (inline SQL for filters, Python for
the proximity refresh, which loads offices into a ~2 km grid and updates businesses in batches).
Lists are paginated, exports stream, rescoring runs in batches.

Imports of more than 2,000 rows run in the background; the Import page polls progress.
Measured on MySQL 8 on a test machine: about 35–60 rows per second including full duplicate checks
(a 3,200-row file where every shop shared one of three Pune PIN codes, with 200 re-listed shops, took
86 seconds and caught all 200 as duplicates). Spread across normal PIN codes it's faster; budget
30–45 minutes for a 100,000-row file. If the server restarts
mid-import, the run is marked "interrupted"; re-upload the file and existing rows are merged.

---

## API reference

| Method | Path | Purpose |
|---|---|---|
| GET | `/businesses` | Search + filters (see below), paginated |
| GET | `/businesses/{id}` | One business |
| POST | `/businesses` | Manual add (cleaned + dedup-checked; returns `outcome`) |
| PUT | `/businesses/{id}` | Partial update: details, categories, lead fields, verification |
| DELETE | `/businesses/{id}` | Delete |
| POST | `/businesses/{id}/check-duplicates` | Show matches for one record |
| GET | `/leads` | Call list (hides Invalid / Do Not Contact / Converted) |
| GET | `/businesses/near-government-offices?radius_m=1000&office_type=…` | Shops near offices |
| GET | `/districts`, `/districts/{id}`, `/districts/{id}/talukas`, `/talukas/{id}/locations` | Geography |
| POST | `/talukas`, `/locations` | Add master data |
| GET | `/filters/cities`, `/filters/areas` | Cascading filter options |
| GET | `/categories`, `/sources`, `/meta` | Reference lists |
| GET | `/analytics`, `/data-quality` | Dashboards (accept district/taluka/city) |
| POST | `/import/csv` | Upload CSV/XLSX of businesses |
| GET | `/import/template` | Blank CSV template |
| POST | `/import/government-offices`, `/import/geo` | Upload offices / talukas & villages |
| GET | `/export/csv` | Filtered CSV export |
| GET | `/duplicates` | Pending/confirmed/rejected pairs |
| POST | `/duplicates/check` | Re-run detection |
| POST | `/duplicates/{id}/confirm`, `/duplicates/{id}/reject` | Resolve a pair |
| GET/POST/PUT/DELETE | `/government-offices` | Offices |
| POST | `/government-offices/recompute-proximity` | Refresh distances + scores |
| POST | `/collection/run` | Google Places search for an area + keyword |
| GET | `/collection/runs`, `/collection/runs/{id}`, `/collection/keywords`, `/collection/status` | Collection log |
| POST | `/admin/rescore` · DELETE `/admin/test-data` · GET `/admin/scoring-rules` | Maintenance |

**Filters** (on `/businesses`, `/leads`, `/export/csv`): `q`, `district`, `taluka`, `city`, `area`,
`pincode`, `category`, `source`, `lead_status` (comma-separated allowed), `verification_status`,
`duplicate_status`, `has_phone`, `has_whatsapp`, `contacted`, `min_score`, `max_score`,
`near_office_m`, `office_type`, `quality_flag`, `followup_due`, `include_test_data`,
`sort` (`score|newest|name|followup|distance`).

## CSV import format

Required: `shop_name`. Recommended: `phone`, `address`, `city`, `taluka`, `district`, `pincode`.
All columns: `shop_name, contact_name, phone, alternate_phone, whatsapp_number, email, address, area,
village, city, taluka, district, pincode, latitude, longitude, google_maps_url, category, source,
source_url` (+ optional `website, source_place_id, rating, review_count, keyword`).
Common header variants are understood (`Mobile`, `Name`, `PIN Code`, `Tehsil`, `Lat`, `Lng`…).

## Security

* `.env` is git-ignored; only `.env.example` is committed.
* Set `API_KEY` in `backend/.env` to require an `X-API-Key` header on every request, and put the same
  value in `frontend/.env` as `VITE_API_KEY`. Leave both blank only on your own machine.
* Exports contain phone numbers — store them carefully and honour "Do Not Contact".

## Database: MySQL (switched from PostgreSQL)

What changed in the code, in case you compare with the old version:

| PostgreSQL feature (old) | MySQL replacement (now) | Where |
|---|---|---|
| `psycopg` driver | `PyMySQL` + `cryptography` | `requirements.txt`, `.env` |
| `JSONB` columns, `@>` containment | `JSON` columns, `JSON_CONTAINS` | `models/business.py`, `utils/sql.py` |
| `pg_trgm` `similarity()` + GIN indexes | `rapidfuzz` on rows pre-filtered by PIN / city | `services/dedup.py` |
| `haversine_m()` SQL function | inline haversine expression / Python | `utils/sql.py`, `services/proximity.py` |
| `UPDATE … FROM … LATERAL` bulk proximity | batched Python update with a ~2 km office grid | `services/proximity.py` |
| `count(*) FILTER (WHERE …)` | `COUNT(CASE WHEN … THEN 1 END)` | `routes/analytics.py` |
| `NULLS LAST` | `ORDER BY col IS NULL, col` | `services/query.py` |
| `lower(city)` index, `ILIKE` | case-insensitive `utf8mb4_unicode_ci` collation | models, migration |
| `TIMESTAMPTZ` | `DATETIME` stored in UTC (session `time_zone = '+00:00'`) | `database.py` |
| `FLOAT8` | `DOUBLE` (MySQL `FLOAT` is too imprecise for coordinates) | models |

The API, CSV formats and frontend are unchanged.
