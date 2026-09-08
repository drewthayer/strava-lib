from .base import ActivityStore

__all__ = ["ActivityStore", "CsvStore", "SheetsStore"]


def __getattr__(name):
    """Resolve the store classes on first use.

    Importing them eagerly would make every entry point pay for both backends'
    dependencies — authorizing or syncing to Sheets would import pandas (via
    CsvStore) and fail if it isn't installed, even though nothing in that path
    touches a DataFrame. Only scripts/backfill_sheets.py needs pandas now.
    """
    if name == "CsvStore":
        from .csv_store import CsvStore

        return CsvStore
    if name == "SheetsStore":
        from .sheets_store import SheetsStore

        return SheetsStore
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
