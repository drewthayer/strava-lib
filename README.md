# strava-lib

Downloads your Strava activity history into a local CSV (one row per
activity) for analysis. Google Sheets export is planned as a second storage
backend once a service account is set up (see `src/strava_lib/storage/sheets_store.py`).

Data is written to `~/projects/strava-data/activities.csv`.

## 1. Create a Strava API application

1. Go to https://www.strava.com/settings/api (log in first).
2. Fill in the form:
   - **Application Name**: anything, e.g. `strava-lib`
   - **Category**: Data Importer (or similar)
   - **Website**: anything, e.g. `http://localhost`
   - **Authorization Callback Domain**: `localhost`
3. Submit. You'll get a **Client ID** and **Client Secret** on the app's settings page.

## 2. Set up the environment

```bash
cd ~/projects/strava-lib
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

Edit `.env` and fill in `STRAVA_CLIENT_ID` and `STRAVA_CLIENT_SECRET` from step 1.

## 3. Authorize (one-time)

Strava uses OAuth2, not a static API key — you need to approve access once in
a browser to get a refresh token, which the app then uses to mint fresh access
tokens automatically.

```bash
python scripts/authorize.py
```

This opens your browser to approve the `activity:read_all` scope (needed to
read private activities and full activity detail), catches the redirect
locally, and prints a `STRAVA_REFRESH_TOKEN` line. Paste that into `.env`.

## 4. Run the sync

```bash
python scripts/sync.py
```

First run fetches your entire activity history; later runs only fetch
activities newer than what's already in the CSV. It's safe to re-run anytime
(e.g. via cron) — it dedupes by activity id.

### About rate limits

Strava's default API limits are 200 requests / 15 min and 2,000 / day. Each
activity requires one detail request (for description, RPE, and segment-effort
PR/KOM tiers), so a large backfill (1,000+ activities) may take more than one
day to fully sync — just re-run `scripts/sync.py` again later and it'll pick
up where it left off. The client automatically waits and retries on 429s.

## What gets captured per activity

Besides the obvious (name, type, date, distance, moving/elapsed time,
elevation gain), each row includes:

- `perceived_exertion` — the RPE you entered
- `workout_type_label` — Race / Long Run / Workout / Default
- `gold_pr_count` / `silver_pr_count` / `bronze_pr_count` — derived from each
  segment effort's `pr_rank`
- `kom_count` / `top10_count` — derived from each segment effort's `kom_rank`
  (rank 1 = KOM/QOM, counted separately from ranks 2-10)
- `description` — the notes/description text on the activity
- heart rate, cadence, power, calories, kudos/comments, gear id, etc.

See `src/strava_lib/models.py` for the full column list.

## Adding Google Sheets later

`src/strava_lib/storage/sheets_store.py` has a stubbed-out `SheetsStore` with
the setup steps in its docstring. Once you've created the service account,
implement its three methods to mirror `CsvStore`, then swap it in via
`strava_lib.sync.run(store=SheetsStore(...))`.
