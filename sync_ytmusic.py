#!/usr/bin/env python3
import sys
from pathlib import Path

from ytmusicapi import YTMusic

from ytmusic_utils import (
    AUTH_JSON, add_in_batches, clean, load_registry, save_registry,
    search_track, strip_version,
)
from spotify2ytmusic import get_token, fetch_playlist


def get_yt_playlist(ytm, playlist_id):
    playlist = ytm.get_playlist(playlist_id, limit=None)
    tracks = []
    for t in playlist.get("tracks", []):
        if t and t.get("videoId"):
            tracks.append({
                "videoId": t["videoId"],
                "setVideoId": t.get("setVideoId"),
                "title": t.get("title", ""),
                "artists": ", ".join(a["name"] for a in t.get("artists", [])),
            })
    return playlist.get("title", ""), tracks


def find_unmatched(spotify_tracks, yt_tracks):
    yt_used = set()

    unmatched_spotify = []
    matched_ids = []

    for st in spotify_tracks:
        s_title = clean(strip_version(st["name"]))
        s_artist = clean(st["artists"])
        found = False
        for i, yt_info in enumerate(yt_tracks):
            if i in yt_used:
                continue
            yt_title = clean(strip_version(yt_info["title"]))
            yt_artist = clean(yt_info["artists"])
            title_match = s_title in yt_title or yt_title in s_title
            artist_match = s_artist in yt_artist or yt_artist in s_artist
            if title_match and artist_match:
                matched_ids.append(yt_info["videoId"])
                yt_used.add(i)
                found = True
                break
        if not found:
            unmatched_spotify.append(st)

    unmatched_yt = [t for i, t in enumerate(yt_tracks) if i not in yt_used]

    return unmatched_spotify, matched_ids, unmatched_yt


def sync(spotify_id, ytmusic_id, sp_dc):
    ytm = YTMusic(AUTH_JSON)

    print("Fetching Spotify playlist...")
    token = get_token(sp_dc)
    name, items = fetch_playlist(token, spotify_id)
    print(f"Spotify: {name} ({len(items)} tracks)")

    yt_name, yt_tracks = get_yt_playlist(ytm, ytmusic_id)
    print(f"YouTube: {yt_name} ({len(yt_tracks)} tracks)")

    spotify_tracks = []
    for item in items:
        if item.get("isLocal"):
            continue
        t = item.get("itemV2", {}).get("data")
        if not t:
            continue
        artists = "; ".join(a["profile"]["name"] for a in t.get("artists", {}).get("items", []))
        album = t.get("albumOfTrack", {})
        spotify_tracks.append({
            "name": t["name"],
            "artists": artists,
            "album": album.get("name", ""),
        })

    unmatched_spotify, matched_ids, unmatched_yt = find_unmatched(spotify_tracks, yt_tracks)

    to_remove = [t for t in unmatched_yt]
    to_add = []

    if unmatched_spotify:
        print(f"\n{len(unmatched_spotify)} track(s) need searching...")
        for st in unmatched_spotify:
            vid, info = search_track(ytm, st)
            if vid:
                to_add.append(vid)
                print(f"  Found: {info}")
            else:
                print(f"  Not found: {st['name']} - {st['artists']}")
    else:
        print("\nAll tracks matched!")

    print(f"\nTo add: {len(to_add)}")
    print(f"To remove: {len(to_remove)}")

    if to_remove:
        print(f"\nRemoving {len(to_remove)} track(s) not in Spotify playlist:")
        for t in to_remove:
            print(f"  - {t['title']} - {t['artists']}")
        yt_set_map = {t["videoId"]: t.get("setVideoId") for t in yt_tracks if t.get("setVideoId")}
        remove_videos = []
        for t in to_remove:
            entry = {"videoId": t["videoId"]}
            if t["videoId"] in yt_set_map:
                entry["setVideoId"] = yt_set_map[t["videoId"]]
            remove_videos.append(entry)

        for i in range(0, len(remove_videos), 25):
            batch = remove_videos[i:i + 25]
            try:
                ytm.remove_playlist_items(ytmusic_id, batch)
                print(f"  Removed batch {min(i + 25, len(remove_videos))}/{len(remove_videos)}")
            except Exception as e:
                print(f"  Failed removing batch: {e}")
        print(f"Removed {len(to_remove)} track(s)")

    if to_add:
        print("\nAdding missing tracks...")
        added, failed = add_in_batches(ytm, ytmusic_id, to_add)
        print(f"Added: {added}, Failed: {failed}")

    print(f"\nURL: https://music.youtube.com/playlist?list={ytmusic_id}")


def interactive_menu(sp_dc):
    import curses

    data = load_registry()

    if not data:
        print("No playlists registered yet.")
        print("Run spotify2ytmusic.py first to create and register playlists.")
        sys.exit(0)

    entries = list(data.items())
    playlist_names = [info["name"] for _, info in entries]
    main_options = playlist_names + ["Sync all", "Exit"]

    def menu(stdscr, options, prompt):
        curses.curs_set(0)
        current = 0

        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, prompt + "\n")
            for i, opt in enumerate(options):
                prefix = "> " if i == current else "  "
                stdscr.addstr(i + 2, 0, f"{prefix}{opt}")
            stdscr.refresh()

            key = stdscr.getch()
            if key == curses.KEY_UP and current > 0:
                current -= 1
            elif key == curses.KEY_DOWN and current < len(options) - 1:
                current += 1
            elif key in (10, 13):
                return current
            elif key == ord('q'):
                return -1

    while True:
        choice = curses.wrapper(menu, main_options, "Select playlist:")

        if choice == -1 or choice == len(main_options) - 1:
            print("Bye!")
            sys.exit(0)

        if choice == len(main_options) - 2:
            print("\nSyncing all playlists...")
            for sid, info in entries:
                print(f"\n{'='*50}")
                sync(sid, info["ytmusic_id"], sp_dc)
            print("\nAll done!")
            sys.exit(0)

        sid, info = entries[choice]
        action = curses.wrapper(menu, ["Sync", "Delete", "Back"], f"{info['name']}:")

        if action == 0:
            print(f"\nSyncing: {info['name']}")
            sync(sid, info["ytmusic_id"], sp_dc)
            print("\nDone!")
            sys.exit(0)
        elif action == 1:
            print(f"Removed: {info['name']}")
            data.pop(sid)
            save_registry(data)
            entries = list(data.items())
            playlist_names = [info["name"] for _, info in entries]
            main_options = playlist_names + ["Sync all", "Exit"]
            if not entries:
                print("All playlists removed.")
                sys.exit(0)


def main():
    if len(sys.argv) == 3:
        sync(sys.argv[1], sys.argv[2], Path("sp_dc.txt").read_text().strip())
        return

    if len(sys.argv) == 2 and sys.argv[1] == "--list":
        data = load_registry()
        if not data:
            print("No playlists registered.")
        else:
            for sid, info in data.items():
                print(f"{info['name']}: {sid} -> {info['ytmusic_id']}")
        return

    sp_dc = Path("sp_dc.txt").read_text().strip()
    if not sp_dc:
        print("Error: sp_dc.txt is empty")
        sys.exit(1)

    interactive_menu(sp_dc)


if __name__ == "__main__":
    main()
