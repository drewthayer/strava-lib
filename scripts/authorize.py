"""One-time OAuth authorization: opens a browser for you to approve access,
catches the redirect locally, and exchanges the code for a refresh token.

Requires STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET to already be set in .env.
Prints the resulting STRAVA_REFRESH_TOKEN to add to .env.
"""

import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from strava_lib import auth, config  # noqa: E402

_captured = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        _captured["code"] = query.get("code", [None])[0]
        _captured["error"] = query.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if _captured.get("code"):
            self.wfile.write(b"<html><body>Authorized. You can close this tab and return to the terminal.</body></html>")
        else:
            self.wfile.write(b"<html><body>Authorization failed or denied. Check the terminal.</body></html>")

    def log_message(self, *args):
        pass


def main():
    if not config.STRAVA_CLIENT_ID or not config.STRAVA_CLIENT_SECRET:
        print("Set STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET in .env first.")
        print("Get them from https://www.strava.com/settings/api")
        sys.exit(1)

    redirect_uri = config.REDIRECT_URI
    parsed = urlparse(redirect_uri)
    server = HTTPServer((parsed.hostname, parsed.port), _Handler)

    url = auth.build_authorize_url(config.STRAVA_CLIENT_ID, redirect_uri, scope=config.SCOPE)
    print(f"Opening browser for Strava authorization:\n{url}\n")
    print("If it doesn't open automatically, paste that URL into a browser.")
    print(f"Waiting for redirect on {redirect_uri} ...")
    webbrowser.open(url)

    server.handle_request()

    code = _captured.get("code")
    if not code:
        print(f"Authorization failed: {_captured.get('error')}")
        sys.exit(1)

    token_data = auth.exchange_code_for_token(config.STRAVA_CLIENT_ID, config.STRAVA_CLIENT_SECRET, code)

    print("\nAuthorization successful. Add this to your .env file:\n")
    print(f"STRAVA_REFRESH_TOKEN={token_data['refresh_token']}")


if __name__ == "__main__":
    main()
