"""Fakes for the Google Sheets backend.

Everything here stands in for gspread objects, so the whole suite runs with no
network, no credentials and no OAuth flow.
"""

import json
import sys
from pathlib import Path

import pytest

# Mirrors what the scripts in scripts/ do, so the suite runs whether or not the
# package has been pip-installed into the environment.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from strava_lib.models import CSV_COLUMNS, build_record  # noqa: E402
from strava_lib.storage import SheetsStore  # noqa: E402


class FakeWorksheet:
    """Stands in for gspread's Worksheet, recording what was asked of it."""

    title = "activities"

    def __init__(self, rows=None, row_count=1000, frozen_row_count=1):
        self.rows = [list(CSV_COLUMNS)] if rows is None else [list(r) for r in rows]
        self.row_count = row_count
        self.frozen_row_count = frozen_row_count
        self.col_count = len(CSV_COLUMNS)
        self.sorted_by = None
        self.calls = []

    def get_all_values(self):
        return [list(r) for r in self.rows]

    def append_rows(self, values, value_input_option=None, insert_data_option=None):
        json.dumps(values)  # the real call has to serialize these to JSON
        assert value_input_option == "RAW", value_input_option
        assert insert_data_option == "INSERT_ROWS", insert_data_option
        self.calls.append(("append_rows", len(values)))
        # Sheets hands values back as display strings, whatever went up.
        self.rows.extend([[str(v) for v in row] for row in values])

    def sort(self, *specs):
        self.sorted_by = specs
        column = specs[0][0] - 1
        self.rows = [self.rows[0]] + sorted(self.rows[1:], key=lambda r: r[column])

    def add_rows(self, count):
        self.calls.append(("add_rows", count))
        self.row_count += count

    def freeze(self, rows=1):
        self.calls.append(("freeze", rows))
        # Sheets' own rule: freezing every visible row is a 400. A header-only
        # grid used to violate it, which broke the first real backfill.
        assert self.row_count > rows, "can't freeze all visible rows on the sheet"
        self.frozen_row_count = rows

    def update(self, range_name=None, values=None):
        self.calls.append(("update", range_name))
        self.rows[:1] = values


class FakeSpreadsheet:
    """Stands in for gspread's Spreadsheet. Missing tabs raise, as gspread does."""

    title = "Strava Activities"
    id = "fake-spreadsheet-id"
    url = "https://example.invalid/fake"

    def __init__(self, worksheet=None):
        self._worksheet = worksheet
        self.created = None

    def worksheet(self, name):
        import gspread

        if self._worksheet is None:
            raise gspread.exceptions.WorksheetNotFound(name)
        return self._worksheet

    def add_worksheet(self, title, rows, cols, index=None):
        self.created = FakeWorksheet(rows=[], row_count=rows, frozen_row_count=0)
        return self.created


@pytest.fixture
def make_store():
    """Build a SheetsStore wired to fakes, bypassing __init__'s auth setup."""

    def build(worksheet=None, spreadsheet=None):
        store = SheetsStore.__new__(SheetsStore)
        store.spreadsheet_id = "fake-spreadsheet-id"
        store.spreadsheet_title = "Strava Activities"
        store.worksheet_name = "activities"
        store.credentials_path = store.token_path = Path("unused.json")
        store.interactive = False
        store._ws = worksheet
        store._spreadsheet = (
            spreadsheet if spreadsheet is not None else FakeSpreadsheet(worksheet)
        )
        store._ids = None
        store._dates = None
        return store

    return build


@pytest.fixture
def activity():
    """Build a record the way sync does, from summary + detail payloads."""

    def build(activity_id, date, name="ride", description="=)"):
        return build_record(
            {
                "id": activity_id, "name": name, "start_date": date,
                "start_date_local": date, "distance": 1000.0,
                "total_elevation_gain": 10.0, "commute": False, "workout_type": 1,
                "start_latlng": [39.7, -105.0],
            },
            {"description": description, "calories": None},
        )

    return build


@pytest.fixture
def sheets_config(tmp_path, monkeypatch):
    """Point the OAuth config at a throwaway client file and token path."""
    from strava_lib import config

    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"installed": {"client_id": "x", "client_secret": "y"}}))
    token = tmp_path / "authorized_user.json"
    monkeypatch.setattr(config, "GOOGLE_SHEETS_CREDENTIALS_PATH", credentials)
    monkeypatch.setattr(config, "GOOGLE_SHEETS_TOKEN_PATH", token)
    monkeypatch.setattr(config, "GOOGLE_SHEETS_SPREADSHEET_ID", None)
    return credentials, token


class FakeCredentials:
    """Stands in for google-auth's user Credentials."""

    def __init__(self, valid=False, refresh_error=None, json_text='{"refreshed": true}'):
        self.valid = valid
        self.refresh_error = refresh_error
        self._json = json_text
        self.refreshed = False

    def refresh(self, request):
        if self.refresh_error is not None:
            raise self.refresh_error
        self.refreshed = True
        self.valid = True

    def to_json(self):
        return self._json


@pytest.fixture
def fake_google_auth(monkeypatch):
    """Replace the google-auth seam with a credentials object of our choosing."""
    from google.auth.exceptions import RefreshError

    from strava_lib.storage import sheets_store

    def install(credentials):
        loaded = {}

        class Credentials:
            @staticmethod
            def from_authorized_user_file(path):
                loaded["path"] = path
                return credentials

        monkeypatch.setattr(
            sheets_store, "_google_auth", lambda: (Credentials, object, RefreshError)
        )
        return loaded

    return install
