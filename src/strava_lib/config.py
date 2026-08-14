import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv, set_key

# Resolved before load_dotenv() so we can write rotated tokens back to the same
# file we read them from. Empty string when there's no .env (e.g. credentials
# supplied directly as environment variables in cron/CI).
DOTENV_PATH = find_dotenv()

load_dotenv(DOTENV_PATH or None)

STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")
STRAVA_REFRESH_TOKEN = os.environ.get("STRAVA_REFRESH_TOKEN")

DATA_DIR = Path(os.environ.get("STRAVA_DATA_DIR", str(Path.home() / "projects" / "strava-data")))
ACTIVITIES_CSV = DATA_DIR / "activities.csv"

REDIRECT_URI = os.environ.get("STRAVA_REDIRECT_URI", "http://localhost:8721/authorized")
SCOPE = "activity:read_all"

GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
GOOGLE_SHEETS_CREDENTIALS_PATH = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")


def save_refresh_token(token):
    """Write a rotated refresh token back to .env so the next run can use it.

    Strava may return a new refresh token on any refresh; the old one stops
    working at that point, so keeping it only in memory would leave a stale
    token in .env and force a re-authorize on the next run.

    Returns True if persisted. Returns False (with a warning) if there's no
    .env to write to — the caller can keep using the token for this process,
    it just won't survive a restart.
    """
    global STRAVA_REFRESH_TOKEN

    STRAVA_REFRESH_TOKEN = token
    os.environ["STRAVA_REFRESH_TOKEN"] = token

    if not DOTENV_PATH:
        print(
            "Warning: Strava rotated the refresh token but no .env file was found "
            "to save it to. Set STRAVA_REFRESH_TOKEN to the new value or the next "
            "run will need to re-authorize."
        )
        return False

    # quote_mode="never" keeps the file in the plain KEY=value style the README
    # tells you to paste into.
    set_key(DOTENV_PATH, "STRAVA_REFRESH_TOKEN", token, quote_mode="never")
    return True
