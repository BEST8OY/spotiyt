import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

from ytmusicapi.setup import setup_browser

from spotiyt.config import AUTH_JSON, COOKIES_JSON, ensure_data_dir
from spotiyt.ui import console, print_error, print_info, print_success, print_warning


def _auth_log(level: str, msg: str, log_cb: Any | None = None):
    if log_cb:
        log_cb(level, msg)
    else:
        if level == "success":
            print_success(msg)
        elif level == "error":
            print_error(msg)
        elif level == "warning":
            print_warning(msg)
        elif level == "info":
            print_info(msg)
        else:
            console.print(msg)


def refresh_from_cookies_json(
    cookies_path: Path | None = None, output_auth: Path | None = None, log_cb: Any | None = None
) -> bool:
    ensure_data_dir()
    path = Path(cookies_path) if cookies_path else COOKIES_JSON
    out_auth = Path(output_auth) if output_auth else AUTH_JSON

    if not path.exists():
        _auth_log("error", f"Cookies file not found: [yellow]{path}[/yellow]", log_cb)
        _auth_log("info", f"Export your YouTube Music cookies in JSON format and save as {path}.", log_cb)
        return False

    if not log_cb and sys.stdout.isatty():
        status_ctx = console.status(f"[bold cyan]Reading cookies from {path}...")
        status_ctx.__enter__()
    else:
        status_ctx = None
        if log_cb:
            log_cb("info", f"Reading cookies from {path}...")

    try:
        with open(path) as f:
            cookies = json.load(f)
    except Exception as e:
        _auth_log("error", f"Failed to parse JSON in {path}: {e}", log_cb)
        return False
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies if "name" in c and "value" in c)

    sapisid = next((c["value"] for c in cookies if c.get("name") == "SAPISID"), None)
    if not sapisid:
        _auth_log(
            "error",
            "SAPISID cookie not found in JSON. Make sure you are logged into YouTube Music when exporting cookies.",
            log_cb,
        )
        return False

    origin = "https://music.youtube.com"
    ts = str(int(time.time()))
    h = hashlib.sha1(f"{ts} {sapisid} {origin}".encode()).hexdigest()
    auth = f"SAPISIDHASH {ts}_{h}"

    headers = "\n".join(
        [
            f"cookie: {cookie_str}",
            "x-goog-authuser: 0",
            f"authorization: {auth}",
            f"origin: {origin}",
            f"referer: {origin}/",
            "x-youtube-client-name: 1",
            "x-youtube-client-version: 2.20240620.01.00",
        ]
    )

    if not log_cb and sys.stdout.isatty():
        status_ctx = console.status(f"[bold cyan]Generating {out_auth}...")
        status_ctx.__enter__()
    else:
        status_ctx = None
        if log_cb:
            log_cb("info", f"Generating {out_auth}...")

    try:
        setup_browser(filepath=str(out_auth), headers_raw=headers)
    except Exception as e:
        _auth_log("error", f"Failed generating auth headers file: {e}", log_cb)
        return False
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    _auth_log(
        "success", f"Successfully generated [bold cyan]{out_auth}[/bold cyan] from [yellow]{path}[/yellow].", log_cb
    )
    return True
