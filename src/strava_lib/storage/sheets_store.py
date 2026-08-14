"""Google Sheets storage backend, via gspread with user OAuth.

Auth mirrors the Strava side of this project: a one-time browser approval, then
a cached refresh token that renews access silently.

1. In the Google Cloud console, enable the Google Sheets API and the Google
   Drive API on a project.
2. APIs & Services -> Credentials -> Create credentials -> OAuth client ID ->
   Desktop app. Download the JSON to GOOGLE_SHEETS_CREDENTIALS_PATH
   (default ~/projects/strava-data/credentials.json).
3. Run `python scripts/authorize_sheets.py` once and approve in the browser.
   The resulting user token is cached at GOOGLE_SHEETS_TOKEN_PATH; later runs
   (including cron) need no browser.

The worksheet is created on first write with a header row matching
models.CSV_COLUMNS exactly. If a worksheet with that name already exists but
has a different header, writes are refused rather than silently misaligning
columns.
"""

import math
import sys

from .. import config
from ..models import CSV_COLUMNS
from .base import ActivityStore

# Sheets caps request size, and a full backfill can be thousands of rows, so
# appends go up in batches rather than one giant request.
APPEND_CHUNK_ROWS = 500

# Header row plus one spare, so the header can be frozen — see _worksheet().
HEADER_AND_SPARE_ROWS = 2

# `spreadsheets` covers everything done to a sheet we know the id of; drive.file
# is the narrow Drive scope that only grants access to files this app created,
# which is all that open-by-title and create need. Deliberately not the full
# `drive` scope gspread defaults to — that would grant read access to the whole
# Drive. Changing this list invalidates the cached token: delete it and re-run
# scripts/authorize_sheets.py.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

DATE_COLUMN_INDEX = CSV_COLUMNS.index("start_date_utc") + 1  # 1-based, for sort()


def _gspread():
    """Import gspread, or explain which interpreter is missing it.

    The scripts put src/ on sys.path themselves, so strava_lib imports fine
    under any Python — including one without the project's dependencies
    installed. Without this, that mistake surfaces as a bare ModuleNotFoundError
    from somewhere deep in a call stack.
    """
    try:
        import gspread
    except ImportError as e:
        raise RuntimeError(
            f"gspread isn't installed for the Python running this script "
            f"({sys.executable}). Either use the project venv "
            f"(.venv/bin/python scripts/...) or install the dependencies into "
            f"this interpreter with `{sys.executable} -m pip install -e .`."
        ) from e
    return gspread


def _cell(value):
    """Coerce one record value into something the Sheets API can serialize.

    None and pandas' NaN both become an empty cell; numpy scalars (which show
    up when records come back out of a DataFrame during backfill) unwrap to
    plain Python ints/floats, which json can encode.
    """
    if value is None:
        return ""
    if hasattr(value, "item"):  # numpy scalar
        value = value.item()
    if isinstance(value, float) and math.isnan(value):
        return ""
    return value


class SheetsStore(ActivityStore):
    def __init__(self, spreadsheet_id=None, credentials_path=None, token_path=None,
                 worksheet_name=None, spreadsheet_title=None, interactive=None):
        self.spreadsheet_id = spreadsheet_id or config.GOOGLE_SHEETS_SPREADSHEET_ID
        self.spreadsheet_title = spreadsheet_title or config.GOOGLE_SHEETS_SPREADSHEET_TITLE
        self.credentials_path = credentials_path or config.GOOGLE_SHEETS_CREDENTIALS_PATH
        self.token_path = token_path or config.GOOGLE_SHEETS_TOKEN_PATH
        self.worksheet_name = worksheet_name or config.GOOGLE_SHEETS_WORKSHEET_NAME
        # Whether we're allowed to open a browser for the one-time approval.
        # Defaults to "only if someone's watching", so a cron run fails with a
        # useful message instead of hanging on a prompt nobody will answer.
        self.interactive = sys.stdin.isatty() if interactive is None else interactive

        # Fail here rather than after printing "opening a browser..."
        _gspread()

        if not self.credentials_path.exists():
            raise RuntimeError(
                f"No Google OAuth client file at {self.credentials_path}. Download a "
                f"Desktop-app OAuth client JSON from the Google Cloud console (see the "
                f"docstring in storage/sheets_store.py), or point "
                f"GOOGLE_SHEETS_CREDENTIALS_PATH at it."
            )
        self._ws = None
        self._spreadsheet = None
        # Sheet reads are a network round-trip each, and sync asks for ids and
        # both date bounds up front, so the sheet is read once and then kept in
        # step with what we append.
        self._ids = None
        self._dates = None

    def __str__(self):
        target = self.spreadsheet_id or f"'{self.spreadsheet_title}'"
        return f"Google Sheet {target} (tab '{self.worksheet_name}')"

    # -- connection ------------------------------------------------------

    def _client(self):
        # Imported lazily so the rest of the package stays importable (and the
        # CSV backfill path usable) without gspread installed.
        gspread = _gspread()

        if not self.token_path.exists() and not self.interactive:
            raise RuntimeError(
                f"Google Sheets isn't authorized yet and there's no terminal to approve "
                f"it in (no cached token at {self.token_path}). Run "
                f"`python scripts/authorize_sheets.py` interactively once, then re-run this."
            )
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        return gspread.oauth(
            scopes=SCOPES,
            credentials_filename=str(self.credentials_path),
            authorized_user_filename=str(self.token_path),
        )

    def spreadsheet(self):
        """Open the target spreadsheet, creating it if only a title was given.

        With user OAuth a created spreadsheet lands in your own Drive, so a
        missing GOOGLE_SHEETS_SPREADSHEET_ID is worth handling rather than
        erroring — it's the zero-setup path.
        """
        if self._spreadsheet is not None:
            return self._spreadsheet

        gspread = _gspread()
        client = self._client()
        try:
            if self.spreadsheet_id:
                self._spreadsheet = client.open_by_key(self.spreadsheet_id)
            else:
                try:
                    self._spreadsheet = client.open(self.spreadsheet_title)
                except gspread.exceptions.SpreadsheetNotFound:
                    self._spreadsheet = client.create(self.spreadsheet_title)
                    print(f"Created spreadsheet '{self.spreadsheet_title}'.")
                    print(
                        f"Pin it by adding this to .env:\n"
                        f"  GOOGLE_SHEETS_SPREADSHEET_ID={self._spreadsheet.id}"
                    )
        except gspread.exceptions.APIError as e:
            raise RuntimeError(
                f"Couldn't open the spreadsheet: {e}. If GOOGLE_SHEETS_SPREADSHEET_ID is "
                f"set, check that the id is right and that the Google account you "
                f"authorized can edit it."
            ) from e
        return self._spreadsheet

    @property
    def url(self):
        return self.spreadsheet().url

    def _worksheet(self):
        if self._ws is not None:
            return self._ws

        gspread = _gspread()
        spreadsheet = self.spreadsheet()
        try:
            ws = spreadsheet.worksheet(self.worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            ws = self._call(
                spreadsheet.add_worksheet,
                title=self.worksheet_name, rows=HEADER_AND_SPARE_ROWS, cols=len(CSV_COLUMNS),
            )
            self._call(ws.update, range_name="A1", values=[CSV_COLUMNS])

        # sort() operates on the whole sheet minus frozen rows, so freezing the
        # header is what keeps it from being sorted into the data.
        #
        # Sheets rejects freezing *every* visible row, so a grid holding nothing
        # but the header can't have that header frozen — widen it by one first.
        # (append_rows grows the grid on its own, so the spare row is only ever
        # briefly empty.)
        if ws.row_count < HEADER_AND_SPARE_ROWS:
            self._call(ws.add_rows, HEADER_AND_SPARE_ROWS - ws.row_count)
        if ws.frozen_row_count < 1:
            self._call(ws.freeze, rows=1)

        self._ws = ws
        return ws

    def _call(self, fn, *args, **kwargs):
        """Run a gspread call, turning API failures into the RuntimeError that
        sync.run() already treats as 'stop cleanly and report progress'."""
        gspread = _gspread()

        try:
            return fn(*args, **kwargs)
        except gspread.exceptions.APIError as e:
            raise RuntimeError(f"Google Sheets API error: {e}") from e

    # -- reads -----------------------------------------------------------

    def _load(self):
        """Read the sheet once, caching activity ids and the start-date bounds."""
        if self._ids is not None:
            return

        ws = self._worksheet()
        rows = self._call(ws.get_all_values)
        if not rows:
            ws.update(range_name="A1", values=[CSV_COLUMNS])
            rows = [CSV_COLUMNS]

        header = rows[0]
        if header != CSV_COLUMNS:
            raise RuntimeError(
                f"Worksheet '{self.worksheet_name}' has a header that doesn't match "
                f"models.CSV_COLUMNS, so appended rows would land in the wrong columns. "
                f"Clear that tab (or point GOOGLE_SHEETS_WORKSHEET_NAME at a new one) and "
                f"re-run. First mismatch: "
                f"{next((f'{a!r} vs expected {b!r}' for a, b in zip(header, CSV_COLUMNS) if a != b), 'column count')}"
            )

        id_col = CSV_COLUMNS.index("id")
        date_col = CSV_COLUMNS.index("start_date_utc")
        ids, dates = set(), []
        for row in rows[1:]:
            if len(row) <= id_col or not row[id_col].strip():
                continue
            try:
                ids.add(int(row[id_col]))
            except ValueError:
                continue
            if len(row) > date_col and row[date_col].strip():
                dates.append(row[date_col])

        self._ids = ids
        self._dates = dates

    def existing_ids(self):
        self._load()
        return set(self._ids)

    def latest_start_date(self):
        self._load()
        return max(self._dates) if self._dates else None

    def oldest_start_date(self):
        self._load()
        return min(self._dates) if self._dates else None

    # -- writes ----------------------------------------------------------

    def append(self, records):
        if not records:
            return
        self._load()

        rows = []
        for record in records:
            activity_id = record.get("id")
            if activity_id is not None:
                activity_id = int(activity_id)
                if activity_id in self._ids:
                    continue
                self._ids.add(activity_id)
            rows.append([_cell(record.get(column)) for column in CSV_COLUMNS])
            start_date = record.get("start_date_utc")
            if start_date is not None and not (isinstance(start_date, float) and math.isnan(start_date)):
                self._dates.append(str(start_date))
        if not rows:
            return

        ws = self._worksheet()
        for i in range(0, len(rows), APPEND_CHUNK_ROWS):
            chunk = rows[i:i + APPEND_CHUNK_ROWS]
            # RAW (not USER_ENTERED) so an activity named "=)" or "+1" is stored
            # as text instead of being parsed as a formula.
            self._call(
                ws.append_rows,
                chunk,
                value_input_option="RAW",
                insert_data_option="INSERT_ROWS",
            )

    def sort(self):
        """Order the sheet oldest-first by start date.

        Rows arrive in whatever order the sync fetched them (newest-first
        forward pass, then walking backward through history), so this is what
        gives the tab a stable chronological ordering.
        """
        if self._ids is not None and not self._ids:
            return
        ws = self._worksheet()
        self._call(ws.sort, (DATE_COLUMN_INDEX, "asc"))
