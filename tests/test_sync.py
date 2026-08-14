"""End-to-end sync against a fake Strava client and a fake sheet."""

import pytest

from strava_lib import sync
from strava_lib.models import CSV_COLUMNS

from conftest import FakeWorksheet

# Strava returns activities newest-first.
SUMMARIES = [
    {"id": 3, "name": "c", "start_date": "2024-03-01T10:00:00Z",
     "start_date_local": "2024-03-01T10:00:00Z", "distance": 1.0,
     "total_elevation_gain": 1.0, "start_latlng": []},
    {"id": 2, "name": "b", "start_date": "2024-02-01T10:00:00Z",
     "start_date_local": "2024-02-01T10:00:00Z", "distance": 1.0,
     "total_elevation_gain": 1.0, "start_latlng": []},
]


class FakeClient:
    """`after` returns nothing (no activities newer than what's stored); the
    unbounded/`before` call walks backward through history."""

    def __init__(self, fail_on_detail=None):
        self.fail_on_detail = fail_on_detail
        self.detail_calls = []

    def get_activities(self, after=None, before=None, per_page=200):
        return iter([] if after else SUMMARIES)

    def get_activity_detail(self, activity_id):
        self.detail_calls.append(activity_id)
        if activity_id == self.fail_on_detail:
            raise RuntimeError("Strava daily rate limit reached (1000/1000)")
        return {"description": f"detail for {activity_id}"}


@pytest.fixture
def client(monkeypatch):
    """Install a fake StravaClient and hand it back for inspection."""
    fake = FakeClient()
    monkeypatch.setattr(sync, "StravaClient", lambda *a, **k: fake)
    return fake


def ids_in(worksheet):
    column = CSV_COLUMNS.index("id")
    return [row[column] for row in worksheet.rows[1:]]


def test_sync_appends_every_activity_and_sorts(make_store, client):
    worksheet = FakeWorksheet()
    store = make_store(worksheet)

    written = sync.run(store=store, detail_pause=0)

    assert written == 2
    assert ids_in(worksheet) == ["2", "3"]  # oldest-first after the sort
    assert worksheet.sorted_by is not None


def test_rerun_resumes_from_the_sheet_and_fetches_nothing(make_store, client):
    worksheet = FakeWorksheet()
    sync.run(store=make_store(worksheet), detail_pause=0)

    written = sync.run(store=make_store(FakeWorksheet(rows=worksheet.rows)), detail_pause=0)

    assert written == 0


def test_rate_limit_keeps_what_was_already_written(make_store, monkeypatch):
    """A stopped run must report its progress and leave the sheet usable, since
    the next run picks up from the dates already stored."""
    fake = FakeClient(fail_on_detail=2)
    monkeypatch.setattr(sync, "StravaClient", lambda *a, **k: fake)
    worksheet = FakeWorksheet()

    written = sync.run(store=make_store(worksheet), detail_pause=0)

    assert written == 1  # activity 3 landed, activity 2 was the one that failed
    assert ids_in(worksheet) == ["3"]
    assert worksheet.sorted_by is not None  # still sorted on the way out


def test_a_sort_failure_does_not_fail_the_run(make_store, client, capsys):
    """Rows are already written by then, so a Sheets blip during the final sort
    is a warning, not a failed sync."""
    worksheet = FakeWorksheet()

    def boom(*a, **k):
        raise RuntimeError("Google Sheets API error: 500")

    worksheet.sort = boom
    written = sync.run(store=make_store(worksheet), detail_pause=0)

    assert written == 2
    assert "couldn't sort" in capsys.readouterr().out
