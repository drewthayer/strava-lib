"""One-time Google Sheets authorization (OAuth).

Opens a browser to approve access to your own Google account, then caches the
resulting user token so `scripts/sync.py` — including from cron — needs no
browser again. Re-run it if you revoke access or delete the token file.

    python scripts/authorize_sheets.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from strava_lib.storage import SheetsStore  # noqa: E402


def main():
    try:
        store = SheetsStore(interactive=True)
        print(f"Using OAuth client {store.credentials_path}")
        print("Opening a browser to approve access...")
        spreadsheet = store.spreadsheet()
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    print(f"\nAuthorized. Token cached at {store.token_path}")
    print(f"Spreadsheet: {spreadsheet.title}")
    print(f"  id:  {spreadsheet.id}")
    print(f"  url: {spreadsheet.url}")
    print("\nNext: python scripts/backfill_sheets.py  (seed it with your existing CSV)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
