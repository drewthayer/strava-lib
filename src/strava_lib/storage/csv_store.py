from pathlib import Path

import pandas as pd

from ..models import CSV_COLUMNS
from .base import ActivityStore


class CsvStore(ActivityStore):
    def __init__(self, path):
        self.path = Path(path)

    def _load(self):
        if self.path.exists():
            return pd.read_csv(self.path)
        return pd.DataFrame(columns=CSV_COLUMNS)

    def existing_ids(self):
        df = self._load()
        if df.empty:
            return set()
        return set(df["id"].tolist())

    def latest_start_date(self):
        df = self._load()
        if df.empty or "start_date_utc" not in df:
            return None
        dates = df["start_date_utc"].dropna()
        return dates.max() if not dates.empty else None

    def oldest_start_date(self):
        df = self._load()
        if df.empty or "start_date_utc" not in df:
            return None
        dates = df["start_date_utc"].dropna()
        return dates.min() if not dates.empty else None

    def append(self, records):
        if not records:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_df = pd.DataFrame(records, columns=CSV_COLUMNS)
        combined = pd.concat([self._load(), new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="id", keep="last")
        combined = combined.sort_values("start_date_utc")
        combined.to_csv(self.path, index=False)
