import json
import hashlib
import time
import sys
from ytmusicapi.setup import setup_browser

def refresh_from_cookies_json(path="cookies.json"):
    with open(path) as f:
        cookies = json.load(f)

    cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies)

    sapisid = next((c["value"] for c in cookies if c["name"] == "SAPISID"), None)
    if not sapisid:
        print("Error: SAPISID cookie not found. Make sure you're logged into YouTube Music.")
        sys.exit(1)

    origin = "https://music.youtube.com"
    ts = str(int(time.time()))
    h = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
    auth = f"SAPISIDHASH {ts}_{h}"

    headers = "\n".join([
        f"cookie: {cookie_str}",
        "x-goog-authuser: 0",
        f"authorization: {auth}",
        f"origin: {origin}",
        f"referer: {origin}/",
        "x-youtube-client-name: 1",
        "x-youtube-client-version: 2.20240620.01.00",
    ])

    setup_browser(filepath="auth.json", headers_raw=headers)
    print("auth.json refreshed successfully")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "cookies.json"
    refresh_from_cookies_json(path)
