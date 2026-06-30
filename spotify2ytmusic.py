#!/usr/bin/env python3
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pyotp
import requests

from ytmusic_utils import (
    import_to_ytmusic, register_playlist,
)

GQL_URL = "https://api-partner.spotify.com/pathfinder/v2/query"
PLAYLIST_HASH = "bb67e0af06e8d6f52b531f97468ee4acd44cd0f82b988e15c2ea47b1148efc77"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
COOKIES_FILE = "spotify_cookies.json"


def datetime_from_unix(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def load_cookies() -> dict:
    path = Path(COOKIES_FILE)
    if not path.exists():
        print(f"Error: {COOKIES_FILE} not found")
        sys.exit(1)
    raw = json.loads(path.read_text())
    return {c["name"]: c["value"] for c in raw}


def get_token(personalized=True) -> str:
    res = requests.get("https://api.github.com/gists/22ed9c6ba463899e933427f7de1f0eef")
    nuances = json.loads(res.json()["files"]["nuances.json"]["content"])
    nuances.sort(key=lambda x: x["v"], reverse=True)
    nuance = nuances[0]

    server_time = requests.get("https://open.spotify.com/api/server-time").json()["serverTime"]
    totp = pyotp.TOTP(nuance["s"])
    code = totp.at(datetime_from_unix(server_time))

    if personalized:
        sp_dc = load_cookies().get("sp_dc", "")
    else:
        sp_dc = "fake_anonymous_token"
    token_url = f"https://open.spotify.com/api/token?reason=transport&productType=web-player&totp={code}&totpServer={code}&totpVer={nuance['v']}"
    res = requests.get(token_url, headers={"Cookie": f"sp_dc={sp_dc}", "User-Agent": UA})
    data = res.json()
    if "accessToken" not in data:
        raise Exception(f"Token failed: {data}")
    label = "personalized" if personalized else "anonymous"
    print(f"Got {label} token ({len(data['accessToken'])} chars)")
    return data["accessToken"]


def fetch_playlist(token: str, playlist_id: str) -> list:
    all_items = []
    offset = 0
    total = 0
    name = ""

    while True:
        for attempt in range(5):
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA}
            res = requests.post(GQL_URL, json={
                "variables": {"uri": f"spotify:playlist:{playlist_id}", "offset": offset, "limit": 100, "enableWatchFeedEntrypoint": False},
                "operationName": "fetchPlaylist",
                "extensions": {"persistedQuery": {"version": 1, "sha256Hash": PLAYLIST_HASH}},
            }, headers=headers)

            if res.status_code in (429, 403):
                print(f"Rate limited ({res.status_code}), waiting 30s...")
                time.sleep(30)
                continue
            res.raise_for_status()
            break
        else:
            raise Exception("Max retries exceeded")

        pv = res.json()["data"]["playlistV2"]
        if offset == 0:
            name = pv["name"]
            total = pv["content"]["totalCount"]
            print(f"Playlist: {name} ({total} tracks)")

        all_items.extend(pv["content"]["items"])
        offset += 100
        print(f"Fetched {len(all_items)}/{total}")
        if offset >= total:
            break
        time.sleep(0.5)

    return name, all_items


def esc(v):
    if v is None:
        return ""
    s = str(v)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def save_csv(name: str, items: list, output: str):
    headers = ["track_name", "artists", "album_name", "album_type", "disc_number", "track_number",
               "duration_ms", "playcount", "explicit", "media_type", "playable", "added_at",
               "added_by", "track_uri", "album_uri", "album_art_url", "spotify_url"]

    full_rows = []
    for item in items:
        if item.get("isLocal"):
            continue
        t = item.get("itemV2", {}).get("data")
        if not t:
            continue
        artists = "; ".join(a["profile"]["name"] for a in t.get("artists", {}).get("items", []))
        track_id = t["uri"].split(":")[-1]
        album = t.get("albumOfTrack", {})
        added_at = (item.get("addedAt") or {}).get("isoString", "")
        added_by = ((item.get("addedBy") or {}).get("data", {}).get("uri", "")).split(":")[-1]
        art_url = (album.get("coverArt", {}).get("sources") or [{}])[0].get("url", "")

        row = [esc(t["name"]), esc(artists), esc(album.get("name")), esc(album.get("type")),
               esc(t.get("discNumber")), esc(t.get("trackNumber")),
               esc(t.get("trackDuration", {}).get("totalMilliseconds")), esc(t.get("playcount")),
               esc(t.get("contentRating", {}).get("label") == "EXPLICIT"), esc(t.get("mediaType")),
               esc(t.get("playability", {}).get("playable")), esc(added_at), esc(added_by),
               esc(t["uri"]), esc(album.get("uri")), esc(art_url),
               f"https://open.spotify.com/track/{track_id}"]
        full_rows.append(",".join(row))

    Path(output).write_text(",".join(headers) + "\n" + "\n".join(full_rows) + "\n")
    print(f"Saved {len(full_rows)} tracks to {output}")
    return output


def sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip().replace(" ", "_")


class Menu:
    def __init__(self, items, prompt):
        self.items = items
        self.prompt = prompt

    def run(self):
        import curses
        return curses.wrapper(self._render)

    def _render(self, stdscr):
        import curses
        curses.curs_set(0)
        current = 0

        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, self.prompt + "\n")
            row = 2
            for i, item in enumerate(self.items):
                if item.get("separator"):
                    stdscr.addstr(row, 0, "  ─────────────────")
                    row += 1
                    continue
                prefix = "> " if i == current else "  "
                stdscr.addstr(row, 0, f"{prefix}{item['label']}")
                row += 1
            stdscr.refresh()

            key = stdscr.getch()
            selectable = [i for i, it in enumerate(self.items) if not it.get("separator")]
            cur_pos = selectable.index(current)

            if key == curses.KEY_UP:
                current = selectable[(cur_pos - 1) % len(selectable)]
            elif key == curses.KEY_DOWN:
                current = selectable[(cur_pos + 1) % len(selectable)]
            elif key in (10, 13):
                return current
            elif key == ord('q'):
                return -1


def get_playlist_ids_interactive():
    input_str = input("Enter playlist ID(s), one per line (empty line to finish):\n")
    ids = []
    while input_str.strip():
        ids.append(input_str.strip())
        input_str = input()
    return ids


def process_playlist(playlist_id, personalized):
    print(f"\n{'='*50}")
    token = get_token(personalized)
    name, items = fetch_playlist(token, playlist_id)
    output = f"{sanitize_filename(name)}.csv"
    save_csv(name, items, output)
    yt_id = import_to_ytmusic(output, f"{name} (Spotify)", "Imported from Spotify")
    register_playlist(playlist_id, yt_id, name)


def main():
    personalized = "--personalized" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--personalized"]

    if len(args) >= 1:
        for playlist_id in args:
            process_playlist(playlist_id, personalized)
        return

    items = [
        {"label": "Enter playlist ID(s) manually"},
        {"separator": True},
        {"label": f"Personalized: {'ON' if personalized else 'OFF'}", "action": "personalized"},
        {"label": "Exit", "action": "exit"},
    ]

    while True:
        menu = Menu(items, "Spotify to YouTube Music:")
        choice = menu.run()

        if choice == -1 or items[choice].get("action") == "exit":
            print("Bye!")
            sys.exit(0)

        if items[choice].get("action") == "personalized":
            personalized = not personalized
            items[1]["label"] = f"Personalized: {'ON' if personalized else 'OFF'}"
            continue

        playlist_ids = get_playlist_ids_interactive()
        if not playlist_ids:
            print("No playlist IDs entered.")
            continue

        for pid in playlist_ids:
            process_playlist(pid, personalized)


if __name__ == "__main__":
    main()
