#!/usr/bin/env python3
import sys
from pathlib import Path

from ytmusicapi import YTMusic

from ytmusic_utils import (
    AUTH_JSON, add_in_batches, clean, load_registry, save_registry,
    search_track, strip_version, _split_artists,
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


def artist_match(spotify_artists, yt_artists):
    s_names = _split_artists(spotify_artists)
    y_names = _split_artists(yt_artists)
    if not s_names or not y_names:
        return False
    matched = sum(1 for a in y_names if a in s_names)
    return matched / len(y_names) >= 0.5


def find_unmatched(spotify_tracks, yt_tracks):
    yt_used = set()
    unmatched_spotify = []
    matched_ids = []

    for st in spotify_tracks:
        s_title = clean(strip_version(st["name"]))
        found = False
        for i, yt_info in enumerate(yt_tracks):
            if i in yt_used:
                continue
            yt_title = clean(strip_version(yt_info["title"]))
            title_ok = s_title in yt_title or yt_title in s_title
            artist_ok = artist_match(st["artists"], yt_info["artists"])
            if title_ok and artist_ok:
                matched_ids.append(yt_info["videoId"])
                yt_used.add(i)
                found = True
                break
        if not found:
            unmatched_spotify.append(st)

    unmatched_yt = [t for i, t in enumerate(yt_tracks) if i not in yt_used]
    return unmatched_spotify, matched_ids, unmatched_yt


def sync(spotify_id, ytmusic_id, sp_dc, preserve=False):
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

    to_remove = [] if preserve else unmatched_yt

    print(f"\nTo add: {len(to_add)}")
    print(f"To remove: {len(to_remove)}")

    if to_remove:
        print(f"\nRemoving {len(to_remove)} track(s) not in Spotify playlist:")
        for t in to_remove:
            print(f"  - {t['title']} - {t['artists']}")
        remove_videos = []
        for t in to_remove:
            entry = {"videoId": t["videoId"]}
            if t.get("setVideoId"):
                entry["setVideoId"] = t["setVideoId"]
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


def build_main_menu(entries, preserve):
    items = []
    for sid, info in entries:
        items.append({"label": info["name"], "sid": sid})
    items.append({"separator": True})
    items.append({"label": f"Preserve extras: {'ON' if preserve else 'OFF'}", "action": "preserve"})
    items.append({"label": "Sync all", "action": "sync_all"})
    items.append({"label": "Delete all", "action": "delete_all"})
    items.append({"label": "Exit", "action": "exit"})
    return items


def interactive_menu(sp_dc, preserve=False):
    data = load_registry()

    if not data:
        print("No playlists registered yet.")
        print("Run spotify2ytmusic.py first to create and register playlists.")
        sys.exit(0)

    entries = list(data.items())
    items = build_main_menu(entries, preserve)

    while True:
        menu = Menu(items, "Select playlist:")
        choice = menu.run()

        if choice == -1:
            print("Bye!")
            sys.exit(0)

        item = items[choice]

        if item.get("action") == "exit":
            print("Bye!")
            sys.exit(0)

        if item.get("action") == "preserve":
            preserve = not preserve
            items = build_main_menu(entries, preserve)
            continue

        if item.get("action") == "sync_all":
            print("\nSyncing all playlists...")
            for sid, info in entries:
                print(f"\n{'='*50}")
                sync(sid, info["ytmusic_id"], sp_dc, preserve)
            print("\nAll done!")
            sys.exit(0)

        if item.get("action") == "delete_all":
            confirm_menu = Menu([
                {"label": "Yes, delete all"},
                {"label": "No, go back"},
            ], "Delete ALL playlists?")
            if confirm_menu.run() == 0:
                save_registry({})
                print(f"Removed all {len(entries)} playlist(s).")
                sys.exit(0)
            continue

        sid = item["sid"]
        info = data[sid]

        sub_menu = Menu([
            {"label": "Sync"},
            {"label": "Delete"},
            {"label": "Back"},
        ], f"{info['name']}:")
        action = sub_menu.run()

        if action == 0:
            print(f"\nSyncing: {info['name']}")
            sync(sid, info["ytmusic_id"], sp_dc, preserve)
            print("\nDone!")
            sys.exit(0)
        elif action == 1:
            print(f"Removed: {info['name']}")
            data.pop(sid)
            save_registry(data)
            entries = list(data.items())
            if not entries:
                print("All playlists removed.")
                sys.exit(0)
            items = build_main_menu(entries, preserve)


def main():
    preserve = "--preserve" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--preserve"]

    if len(args) == 2:
        sync(args[0], args[1], Path("sp_dc.txt").read_text().strip(), preserve)
        return

    if len(args) == 1 and args[0] == "--list":
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

    interactive_menu(sp_dc, preserve)


if __name__ == "__main__":
    main()
