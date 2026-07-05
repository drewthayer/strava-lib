from abc import ABC, abstractmethod


class ActivityStore(ABC):
    """Interface shared by CsvStore and (later) SheetsStore."""

    @abstractmethod
    def existing_ids(self):
        """Return the set of activity ids already stored."""

    @abstractmethod
    def latest_start_date(self):
        """Return the max start_date_utc already stored, or None if empty."""

    @abstractmethod
    def oldest_start_date(self):
        """Return the min start_date_utc already stored, or None if empty."""

    @abstractmethod
    def append(self, records):
        """Merge new records in, deduping by id."""
