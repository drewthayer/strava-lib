"""Copy the activities already in the local CSV into the Google Sheet.

Run this once, before the first sheets-backed sync. The sheet is now both the
output and the record of what's been downloaded, so an empty sheet would send
sync.py back to Strava for your entire history — days of work against the API
rate limit, for data already sitting in the CSV.

Safe to re-run: rows whose activity id is already in the sheet are skipped.

    python scripts/backfill_sheets.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from strava_lib import config  # noqa: E402
from strava_lib.models import CSV_COLUMNS  # noqa: E402
from strava_lib.storage import SheetsStore  # noqa: E402


def main():
    csv_path = config.ACTIVITIES_CSV
    if not csv_path.exists():
        print(f"No CSV at {csv_path} — nothing to backfill.")
        return 0

    df = pd.read_csv(csv_path).reindex(columns=CSV_COLUMNS)
    records = [r for r in df.to_dict("records") if pd.notna(r["id"])]

    try:
        sheets = SheetsStore()
        already = sheets.existing_ids()
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    pending = [r for r in records if int(r["id"]) not in already]

    print(f"{len(records)} rows in {csv_path}; {len(already)} already in the sheet.")
    if not pending:
        print("Sheet is already up to date.")
        return 0

    print(f"Appending {len(pending)} rows to {sheets}...")
    try:
        sheets.append(pending)
        print("Sorting by start date...")
        sheets.sort()
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1
    print(f"Done. Sheet now has {len(sheets.existing_ids())} activities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
