import time

import requests

from . import auth, config

API_BASE = "https://www.strava.com/api/v3"


class StravaClient:
    def __init__(self, client_id=None, client_secret=None, refresh_token=None):
        self.client_id = client_id or config.STRAVA_CLIENT_ID
        self.client_secret = client_secret or config.STRAVA_CLIENT_SECRET
        self.refresh_token = refresh_token or config.STRAVA_REFRESH_TOKEN
        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise RuntimeError(
                "Missing Strava credentials. Set STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, "
                "and STRAVA_REFRESH_TOKEN in .env (run scripts/authorize.py to generate a "
                "refresh token)."
            )
        self._access_token = None
        self._expires_at = 0

    def _ensure_token(self):
        if self._access_token and time.time() < self._expires_at - 60:
            return
        data = auth.refresh_access_token(self.client_id, self.client_secret, self.refresh_token)
        self._access_token = data["access_token"]
        self._expires_at = data["expires_at"]
        if data.get("refresh_token"):
            self.refresh_token = data["refresh_token"]

    def _request(self, method, path, **kwargs):
        self._ensure_token()
        url = f"{API_BASE}{path}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"
        while True:
            resp = requests.request(method, url, headers=headers, **kwargs)
            if resp.status_code == 429:
                self._handle_rate_limit(resp)
                continue
            resp.raise_for_status()
            return resp

    @staticmethod
    def _handle_rate_limit(resp):
        """Strava doesn't send Retry-After. Non-approved apps also have a lower
        read-specific limit (X-ReadRateLimit-*) on top of the general one, so
        check both. If the *daily* bucket is exhausted, fail fast instead of
        polling for hours; if it's just the 15-minute bucket, sleep out the window."""
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            wait = int(retry_after)
            print(f"Rate limited by Strava; waiting {wait}s...")
            time.sleep(wait)
            return

        for header in ("X-ReadRateLimit-Usage", "X-RateLimit-Usage"):
            usage = resp.headers.get(header)
            limit = resp.headers.get(header.replace("Usage", "Limit"))
            if not usage or not limit:
                continue
            _, daily_usage = (int(x) for x in usage.split(","))
            _, daily_limit = (int(x) for x in limit.split(","))
            if daily_usage >= daily_limit:
                raise RuntimeError(
                    f"Strava daily rate limit reached ({daily_usage}/{daily_limit} via {header}). "
                    "Re-run this later (limit resets at midnight UTC)."
                )

        wait = 15 * 60
        print(f"Strava 15-minute rate limit reached; waiting {wait}s for the window to reset...")
        time.sleep(wait)

    def get_activities(self, after=None, before=None, per_page=200):
        """Yield summary activity dicts, newest first (Strava's default order).

        `after`/`before` (epoch seconds) bound the range once, at the start of
        pagination — `page` increments within that fixed bound as we walk
        further back in time."""
        page = 1
        while True:
            params = {"page": page, "per_page": per_page}
            if after:
                params["after"] = int(after)
            if before:
                params["before"] = int(before)
            resp = self._request("GET", "/athlete/activities", params=params)
            batch = resp.json()
            if not batch:
                return
            for activity in batch:
                yield activity
            page += 1
            time.sleep(0.3)

    def get_activity_detail(self, activity_id):
        """Fetch the detailed activity, including all segment efforts (for PR/KOM tiers)."""
        resp = self._request(
            "GET", f"/activities/{activity_id}", params={"include_all_efforts": True}
        )
        return resp.json()
