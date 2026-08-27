import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

from ytmusicapi.setup import setup_browser
from spotiyt.ui import console, print_banner, print_success, print_error, print_warning, print_info


def refresh_from_cookies_json(cookies_path: str = "ytm-cookies.json", output_auth: str = "auth.json"):
    path = Path(cookies_path)
    if not path.exists():
        print_error(f"Cookies file not found: [yellow]{cookies_path}[/yellow]")
        print_info("Export your YouTube Music cookies in JSON format (e.g., using Cookie-Editor extension) and save as ytm-cookies.json.")
        sys.exit(1)

    with console.status(f"[bold cyan]Reading cookies from {cookies_path}..."):
        try:
            with open(path) as f:
                cookies = json.load(f)
        except Exception as e:
            print_error(f"Failed to parse JSON in {cookies_path}: {e}")
            sys.exit(1)

    cookie_str = "; ".join(f'{c["name"]}={c["value"]}' for c in cookies)

    sapisid = next((c["value"] for c in cookies if c["name"] == "SAPISID"), None)
    if not sapisid:
        print_error("SAPISID cookie not found in JSON. Make sure you are logged into YouTube Music when exporting cookies.")
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

    with console.status(f"[bold cyan]Generating {output_auth}..."):
        setup_browser(filepath=output_auth, headers_raw=headers)

    print_success(f"Successfully generated [bold cyan]{output_auth}[/bold cyan] from [yellow]{cookies_path}[/yellow].")
