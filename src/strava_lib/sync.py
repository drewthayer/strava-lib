import time
from datetime import datetime

from . import config
from .client import StravaClient
from .models import build_record
from .storage.csv_store import CsvStore


def _to_epoch(date_str):
    if not date_str:
        return None
    dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
    return int(dt.timestamp())


def _fetch_and_write(client, store, existing_ids, activities, detail_pause, counter):
    """Fetch detail for each summary activity and write it to `store`
    immediately, incrementing `counter[0]` as it goes. Lets RuntimeError
    (rate limit) propagate — whatever was fetched before that is already
    safely on disk and already counted, since the increment happens before
    any further network call that could fail."""
    for summary in activities:
        activity_id = summary.get("id")
        if activity_id in existing_ids:
            continue
        detail = client.get_activity_detail(activity_id)
        record = build_record(summary, detail)
        store.append([record])
        existing_ids.add(activity_id)
        counter[0] += 1
        print(f"Wrote activity {activity_id}: {summary.get('name')} ({summary.get('start_date_local')})")
        time.sleep(detail_pause)


def run(store=None, detail_pause=0.5):
    """Two-phase sync, safe to interrupt and re-run at any point:

    1. Forward — fetch anything newer than the most recent activity already
       stored (catches new activities since your last sync).
    2. Backward — page further into history from the oldest activity already
       stored (continues an interrupted backfill).

    Strava returns activities newest-first, so resuming a backfill with an
    `after` cursor set to the newest saved date would return nothing — every
    remaining un-fetched activity is *older*, not newer. Phase 2 uses `before`
    against the oldest saved date instead, so it keeps walking backward.

    Both phases write each activity to `store` as soon as it's fetched, so a
    rate limit or crash only costs the activity in flight.
    """
    store = store or CsvStore(config.ACTIVITIES_CSV)
    client = StravaClient()
    existing_ids = store.existing_ids()
    counter = [0]

    latest = store.latest_start_date()
    oldest = store.oldest_start_date()

    try:
        if latest:
            _fetch_and_write(
                client, store, existing_ids,
                client.get_activities(after=_to_epoch(latest)),
                detail_pause, counter,
            )
        _fetch_and_write(
            client, store, existing_ids,
            client.get_activities(before=_to_epoch(oldest)),
            detail_pause, counter,
        )
    except RuntimeError as e:
        print(f"\nStopped early: {e}")
        print(f"{counter[0]} new activities written this run. Re-run scripts/sync.py to continue.")
        return counter[0]

    print(f"Done. {counter[0]} new activities written to {getattr(store, 'path', store)}")
    return counter[0]
