# strava-lib

Downloads your Strava activity history into a Google Sheet, one row per
activity, for analysis. New activities are appended to the sheet on each run.

The sheet is also the record of what's already been downloaded, so re-running is
cheap and safe. See [Google Sheets setup](#google-sheets-setup) — it needs a
one-time browser authorization, same as Strava.

Older versions wrote to `~/projects/strava-data/activities.csv`. That file is now
only read, by `scripts/backfill_sheets.py`, to seed the sheet with history you've
already downloaded.

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

The scripts add `src/` to `sys.path` themselves, so `strava_lib` imports under any
interpreter — but its dependencies only exist in the venv. In a shell where you
haven't activated it, run the scripts as `.venv/bin/python scripts/...` rather
than bare `python`.

## 3. Authorize Strava (one-time)

Strava uses OAuth2, not a static API key — you need to approve access once in
a browser to get a refresh token, which the app then uses to mint fresh access
tokens automatically.

```bash
python scripts/authorize.py
```

This opens your browser to approve the `activity:read_all` scope (needed to
read private activities and full activity detail), catches the redirect
locally, and prints a `STRAVA_REFRESH_TOKEN` line. Paste that into `.env`.

## 4. Google Sheets setup

Writing goes through [gspread](https://docs.gspread.org/) using OAuth against
your own Google account — the sheet lands in your Drive and you can open it
normally.

### 4a. Create an OAuth client

1. In the [Google Cloud console](https://console.cloud.google.com/), create (or
   pick) a project.
2. Enable both the **Google Sheets API** and the **Google Drive API** on it.
3. **APIs & Services → OAuth consent screen**: set it up as **External**, and
   add your own Google account under **Test users** (a personal-use app stays in
   testing mode, which only test users can authorize).
4. **APIs & Services → Credentials → Create credentials → OAuth client ID →
   Desktop app**. Download the JSON to
   `~/projects/strava-data/credentials.json` — that path is already the default,
   so nothing goes in `.env`.

### 4b. Authorize (one-time)

```bash
python scripts/authorize_sheets.py
```

This opens a browser for approval, then caches a user token at
`~/projects/strava-data/authorized_user.json`, so later runs — including from
cron — need no browser. It prints the spreadsheet's id and URL when it's done.

By default it uses the sheet titled **Strava Activities** in your Drive and
creates it if it isn't there. To target a sheet you already have, put its id
(the long token in its URL between `/d/` and `/edit`) in `.env` as
`GOOGLE_SHEETS_SPREADSHEET_ID`.

The requested scopes are `spreadsheets` plus `drive.file`, the narrow Drive scope
covering only files this app created — not the full-Drive scope gspread defaults
to. If you ever change `SCOPES` in `storage/sheets_store.py`, delete the cached
token and re-run this script.

**Set the publishing status to "In production."** While the consent screen sits in
**Testing**, Google expires the refresh token after 7 days, so the cached token
dies weekly and a cron sync starts failing with an auth error until you re-run
this script in a browser. Publishing removes the expiry; for a single-user app you
can do it without verification, at the cost of one "unverified app" warning at the
consent screen (click through via *Advanced*).

### 4c. Seed the sheet from the existing CSV

```bash
python scripts/backfill_sheets.py
```

The sheet is now both the output and the record of what's been downloaded, so an
empty sheet would send the sync back to Strava for your entire history — days of
work against the rate limit for data already in `activities.csv`. This copies it
up in one pass. It's idempotent (ids already in the sheet are skipped), so it's
also how to re-fill a sheet you cleared.

The tab is created with a header row matching `models.CSV_COLUMNS`, frozen. If a
tab by that name already exists with a different header, writes are refused
rather than dropping values into the wrong columns — clear that tab, or point
`GOOGLE_SHEETS_WORKSHEET_NAME` at a new one.

## 5. Run the sync

```bash
python scripts/sync.py
```

First run fetches your entire activity history; later runs only fetch activities
newer than the newest row in the sheet. It's safe to re-run anytime (e.g. via
cron) — it dedupes by activity id.

Each activity is appended as soon as it's fetched, so an interrupted run leaves
the sheet consistent and the next run picks up where it stopped. Rows arrive in
fetch order and get sorted oldest-first by `start_date_utc` at the end of a run.

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
