"""Google Sheets storage backend — not implemented yet.

Once the Google Cloud service account exists:
1. Enable the Google Sheets API on the GCP project.
2. Create a service account, download its JSON key.
3. Share the target spreadsheet with the service account's email as an Editor.
4. Set GOOGLE_SHEETS_SPREADSHEET_ID and GOOGLE_SHEETS_CREDENTIALS_PATH in .env.
5. `pip install gspread google-auth`, then implement the methods below to mirror
   CsvStore's semantics (dedupe by id, sort by start_date_utc).
"""

from .base import ActivityStore


class SheetsStore(ActivityStore):
    def __init__(self, spreadsheet_id=None, credentials_path=None, worksheet_name="activities"):
        self.spreadsheet_id = spreadsheet_id
        self.credentials_path = credentials_path
        self.worksheet_name = worksheet_name

    def existing_ids(self):
        raise NotImplementedError("SheetsStore is not implemented yet — see module docstring.")

    def latest_start_date(self):
        raise NotImplementedError("SheetsStore is not implemented yet — see module docstring.")

    def oldest_start_date(self):
        raise NotImplementedError("SheetsStore is not implemented yet — see module docstring.")

    def append(self, records):
        raise NotImplementedError("SheetsStore is not implemented yet — see module docstring.")
