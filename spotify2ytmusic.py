#!/usr/bin/env python3
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pyotp
import requests
from ytmusicapi import YTMusic

from ytmusic_utils import (
    AUTH_JSON, add_in_batches, deduplicate, load_tracks, register_playlist,
    save_dropped, save_not_found, search_tracks, verify_playlist,
)

GQL_URL = "https://api-partner.spotify.com/pathfinder/v2/query"
PLAYLIST_HASH = "bb67e0af06e8d6f52b531f97468ee4acd44cd0f82b988e15c2ea47b1148efc77"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"


def datetime_from_unix(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def get_token(sp_dc: str) -> str:
    res = requests.get("https://api.github.com/gists/22ed9c6ba463899e933427f7de1f0eef")
    nuances = json.loads(res.json()["files"]["nuances.json"]["content"])
    nuances.sort(key=lambda x: x["v"], reverse=True)
    nuance = nuances[0]

    server_time = requests.get("https://open.spotify.com/api/server-time").json()["serverTime"]
    totp = pyotp.TOTP(nuance["s"])
    code = totp.at(datetime_from_unix(server_time))

    token_url = f"https://open.spotify.com/api/token?reason=transport&productType=web-player&totp={code}&totpServer={code}&totpVer={nuance['v']}"
    res = requests.get(token_url, headers={"Cookie": f"sp_dc={sp_dc}", "User-Agent": UA})
    data = res.json()
    if "accessToken" not in data:
        raise Exception(f"Token failed: {data}")
    print(f"Got token ({len(data['accessToken'])} chars)")
    return data["accessToken"]


def fetch_playlist(token: str, playlist_id: str) -> list:
    all_items = []
    offset = 0
    total = 0
    name = ""

    while True:
        for attempt in range(5):
            res = requests.post(GQL_URL, json={
                "variables": {"uri": f"spotify:playlist:{playlist_id}", "offset": offset, "limit": 100, "enableWatchFeedEntrypoint": False},
                "operationName": "fetchPlaylist",
                "extensions": {"persistedQuery": {"version": 1, "sha256Hash": PLAYLIST_HASH}},
            }, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": UA})

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


def import_ytmusic(csv_file: str, playlist_name: str):
    ytm = YTMusic(AUTH_JSON)

    tracks = load_tracks(csv_file)
    print(f"Loaded {len(tracks)} tracks")
    playlist_id = ytm.create_playlist(title=playlist_name, description="Imported from Spotify")
    print(f"Created playlist: {playlist_name}")

    found_videos, not_found = search_tracks(ytm, tracks)
    print(f"\nFound {len(found_videos)}/{len(tracks)} tracks on YouTube Music")

    save_not_found(csv_file, not_found)

    if found_videos:
        unique, _ = deduplicate(found_videos)
        unique_ids = [v[0] for v in unique]
        added, failed = add_in_batches(ytm, playlist_id, unique_ids)
        print(f"\nAdded: {added}, Failed: {failed}")

        missing = verify_playlist(ytm, playlist_id, unique_ids)
        save_dropped(csv_file, tracks, [v[0] for v in found_videos], missing)

    print(f"URL: https://music.youtube.com/playlist?list={playlist_id}")
    return playlist_id


def sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in " _-" else "_" for c in name).strip().replace(" ", "_")


def main():
    if len(sys.argv) < 2:
        print("Usage: python spotify2ytmusic.py <playlist_id> [playlist_id2] ...")
        print("sp_dc token is read from sp_dc.txt")
        sys.exit(1)

    sp_dc = Path("sp_dc.txt").read_text().strip()
    if not sp_dc:
        print("Error: sp_dc.txt is empty")
        sys.exit(1)

    playlist_ids = sys.argv[1:]

    token = get_token(sp_dc)

    for playlist_id in playlist_ids:
        print(f"\n{'='*50}")
        name, items = fetch_playlist(token, playlist_id)
        output = f"{sanitize_filename(name)}.csv"
        save_csv(name, items, output)
        yt_id = import_ytmusic(output, f"{name} (Spotify)")
        register_playlist(playlist_id, yt_id, name)


if __name__ == "__main__":
    main()
