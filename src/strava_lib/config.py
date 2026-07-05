import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

STRAVA_CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
STRAVA_CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")
STRAVA_REFRESH_TOKEN = os.environ.get("STRAVA_REFRESH_TOKEN")

DATA_DIR = Path(os.environ.get("STRAVA_DATA_DIR", str(Path.home() / "projects" / "strava-data")))
ACTIVITIES_CSV = DATA_DIR / "activities.csv"

REDIRECT_URI = os.environ.get("STRAVA_REDIRECT_URI", "http://localhost:8721/authorized")
SCOPE = "activity:read_all"

GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID")
GOOGLE_SHEETS_CREDENTIALS_PATH = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_PATH")
