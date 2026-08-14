import pandas as pd
import pytest

from strava_lib.models import CSV_COLUMNS
from strava_lib.storage import CsvStore, SheetsStore
from strava_lib.storage.sheets_store import APPEND_CHUNK_ROWS, SCOPES

from conftest import FakeSpreadsheet, FakeWorksheet

DATE_COLUMN = CSV_COLUMNS.index("start_date_utc") + 1


def column(row, name):
    return row[CSV_COLUMNS.index(name)]


# -- reads -----------------------------------------------------------------


def test_empty_sheet_reports_no_ids_or_bounds(make_store):
    store = make_store(FakeWorksheet())
    assert store.existing_ids() == set()
    assert store.latest_start_date() is None
    assert store.oldest_start_date() is None


def test_sort_is_skipped_when_there_is_nothing_to_order(make_store):
    worksheet = FakeWorksheet()
    store = make_store(worksheet)
    store.existing_ids()
    store.sort()
    assert worksheet.sorted_by is None


def test_existing_rows_are_read_back_ignoring_blank_rows(make_store, activity):
    rows = [CSV_COLUMNS]
    for record in (activity(1, "2024-01-01T10:00:00Z"), activity(2, "2024-02-01T10:00:00Z")):
        rows.append([str(record[c]) for c in CSV_COLUMNS])
    rows.append([""] * len(CSV_COLUMNS))  # the spare row Sheets needs to freeze a header

    store = make_store(FakeWorksheet(rows=rows))
    assert store.existing_ids() == {1, 2}
    assert store.oldest_start_date() == "2024-01-01T10:00:00Z"
    assert store.latest_start_date() == "2024-02-01T10:00:00Z"


def test_mismatched_header_is_refused(make_store):
    worksheet = FakeWorksheet(rows=[["id", "nope"] + CSV_COLUMNS[2:]])
    store = make_store(worksheet)
    with pytest.raises(RuntimeError, match="doesn't match"):
        store.existing_ids()


# -- writes ----------------------------------------------------------------


def test_append_writes_rows_and_tracks_bounds(make_store, activity):
    worksheet = FakeWorksheet()
    store = make_store(worksheet)

    store.append([activity(3, "2024-03-01T10:00:00Z"), activity(1, "2024-01-01T10:00:00Z")])
    store.append([activity(2, "2024-02-01T10:00:00Z")])

    assert store.existing_ids() == {1, 2, 3}
    assert store.oldest_start_date() == "2024-01-01T10:00:00Z"
    assert store.latest_start_date() == "2024-03-01T10:00:00Z"
    assert len(worksheet.rows) == 4  # header + 3


def test_append_skips_ids_already_present(make_store, activity):
    worksheet = FakeWorksheet()
    store = make_store(worksheet)
    store.append([activity(1, "2024-01-01T10:00:00Z")])

    store.append([activity(1, "2024-01-01T10:00:00Z")])

    assert len(worksheet.rows) == 2  # header + the one row
    assert store.existing_ids() == {1}


def test_append_of_nothing_touches_no_api(make_store):
    worksheet = FakeWorksheet()
    make_store(worksheet).append([])
    assert worksheet.calls == []


def test_missing_values_become_empty_cells_and_text_stays_text(make_store, activity):
    worksheet = FakeWorksheet()
    store = make_store(worksheet)

    store.append([activity(1, "2024-01-01T10:00:00Z", name="+1")])

    row = worksheet.rows[1]
    assert column(row, "calories") == ""  # None, not "None"
    # RAW input, so a leading "=" or "+" is stored rather than parsed as a formula
    assert column(row, "description") == "=)"
    assert column(row, "name") == "+1"


def test_large_appends_are_chunked(make_store, activity):
    worksheet = FakeWorksheet()
    store = make_store(worksheet)
    records = [activity(i, f"2024-01-01T10:00:{i % 60:02d}Z") for i in range(APPEND_CHUNK_ROWS + 10)]

    store.append(records)

    appends = [c for c in worksheet.calls if c[0] == "append_rows"]
    assert appends == [("append_rows", APPEND_CHUNK_ROWS), ("append_rows", 10)]
    assert len(store.existing_ids()) == APPEND_CHUNK_ROWS + 10


def test_dataframe_records_survive_the_round_trip(make_store, activity, tmp_path):
    """The backfill path hands over pandas records: NaN and numpy scalars, which
    the Sheets API can't serialize as-is."""
    csv_path = tmp_path / "activities.csv"
    CsvStore(csv_path).append([activity(9, "2024-04-01T10:00:00Z")])
    records = pd.read_csv(csv_path).reindex(columns=CSV_COLUMNS).to_dict("records")

    worksheet = FakeWorksheet()
    store = make_store(worksheet)
    store.append(records)  # would raise on numpy int64 / NaN

    assert store.existing_ids() == {9}
    assert column(worksheet.rows[1], "calories") == ""  # NaN -> empty cell


def test_sort_orders_oldest_first_by_start_date(make_store, activity):
    worksheet = FakeWorksheet()
    store = make_store(worksheet)
    store.append([activity(3, "2024-03-01T10:00:00Z"), activity(1, "2024-01-01T10:00:00Z")])

    store.sort()

    assert worksheet.sorted_by == ((DATE_COLUMN, "asc"),)
    assert [column(r, "id") for r in worksheet.rows[1:]] == ["1", "3"]


# -- worksheet setup -------------------------------------------------------


def test_new_tab_gets_a_header_and_a_frozen_row(make_store):
    spreadsheet = FakeSpreadsheet()  # no tab yet
    store = make_store(spreadsheet=spreadsheet)

    worksheet = store._worksheet()

    assert worksheet.rows[0] == CSV_COLUMNS
    assert worksheet.frozen_row_count == 1
    # created wide enough to freeze a row, so no resize needed
    assert ("add_rows", 1) not in worksheet.calls


def test_header_only_tab_is_widened_before_freezing(make_store):
    """Sheets 400s on freezing every visible row, so a tab holding nothing but
    the header can't have it frozen until the grid grows."""
    stuck = FakeWorksheet(rows=[CSV_COLUMNS], row_count=1, frozen_row_count=0)
    store = make_store(spreadsheet=FakeSpreadsheet(stuck))

    store._worksheet()

    assert ("add_rows", 1) in stuck.calls
    assert stuck.frozen_row_count == 1
    assert store.existing_ids() == set()


def test_already_frozen_tab_is_left_alone(make_store):
    ready = FakeWorksheet(rows=[CSV_COLUMNS], row_count=500, frozen_row_count=1)
    store = make_store(spreadsheet=FakeSpreadsheet(ready))

    store._worksheet()

    assert ready.calls == []


def test_api_errors_become_runtime_errors(make_store):
    import gspread

    worksheet = FakeWorksheet()
    store = make_store(worksheet)

    class Response:
        status_code = 429
        text = "quota exceeded"

        def json(self):
            return {"error": {"message": "quota exceeded", "code": 429}}

    def boom():
        raise gspread.exceptions.APIError(Response())

    with pytest.raises(RuntimeError, match="Google Sheets API error"):
        store._call(boom)


# -- auth ------------------------------------------------------------------


def test_missing_oauth_client_file_is_explained(sheets_config, monkeypatch):
    from strava_lib import config

    monkeypatch.setattr(
        config, "GOOGLE_SHEETS_CREDENTIALS_PATH", sheets_config[0].parent / "absent.json"
    )
    with pytest.raises(RuntimeError, match="No Google OAuth client file"):
        SheetsStore()


def test_uncached_token_without_a_terminal_does_not_open_a_browser(sheets_config):
    """A cron run must fail with an explanation rather than hang on a browser
    approval nobody is there to click."""
    store = SheetsStore(interactive=False)
    with pytest.raises(RuntimeError, match="isn't authorized yet"):
        store.spreadsheet()


def test_config_supplies_the_defaults(sheets_config):
    credentials, token = sheets_config
    store = SheetsStore(interactive=False)
    assert store.credentials_path == credentials
    assert store.token_path == token
    assert store.spreadsheet_title == "Strava Activities"
    assert store.worksheet_name == "activities"


def test_scopes_stay_narrow():
    """drive.file grants access only to files this app created; the full `drive`
    scope gspread defaults to would expose the user's whole Drive."""
    assert SCOPES == [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
