#!/usr/bin/env python3
import sys
from pathlib import Path

from ytmusicapi import YTMusic

from ytmusic_utils import (
    AUTH_JSON, add_in_batches, clean, load_registry, search_tracks,
    strip_version,
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


def quick_match(spotify_tracks, yt_tracks):
    if len(spotify_tracks) != len(yt_tracks):
        return False

    yt_set = {(clean(strip_version(t["title"])), clean(t["artists"])) for t in yt_tracks}

    for st in spotify_tracks:
        key = (clean(strip_version(st["name"])), clean(st["artists"]))
        if key not in yt_set:
            return False

    return True


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

    if quick_match(spotify_tracks, yt_tracks):
        print("\nPlaylists are already in sync!")
        return

    print(f"\nSearching {len(spotify_tracks)} Spotify tracks on YouTube Music...")
    found_videos, not_found = search_tracks(ytm, spotify_tracks)

    if not_found:
        print(f"\n{len(not_found)} track(s) not found on YouTube Music:")
        for t in not_found:
            print(f"  - {t['name']} - {t['artists']}")

    yt_video_ids = {t["videoId"] for t in yt_tracks}
    yt_set_map = {t["videoId"]: t["setVideoId"] for t in yt_tracks if t.get("setVideoId")}
    found_ids = {v[0] for v in found_videos}

    to_add = found_ids - yt_video_ids
    to_remove = yt_video_ids - found_ids

    print(f"\nTo add: {len(to_add)}")
    print(f"To remove: {len(to_remove)}")

    if to_remove:
        print("\nRemoving tracks not in Spotify playlist...")
        remove_videos = []
        for vid in to_remove:
            entry = {"videoId": vid}
            if vid in yt_set_map:
                entry["setVideoId"] = yt_set_map[vid]
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
        add_ids = [v[0] for v in found_videos if v[0] in to_add]
        added, failed = add_in_batches(ytm, ytmusic_id, add_ids)
        print(f"Added: {added}, Failed: {failed}")

    print(f"\nURL: https://music.youtube.com/playlist?list={ytmusic_id}")


def interactive_menu(sp_dc):
    data = load_registry()

    if not data:
        print("No playlists registered yet.")
        print("Run spotify2ytmusic.py first to create and register playlists.")
        sys.exit(0)

    print("\nRegistered playlists:\n")
    entries = list(data.items())
    for i, (sid, info) in enumerate(entries, 1):
        print(f"  {i}. {info['name']}")
        print(f"     Spotify: {sid}")
        print(f"     YouTube: {info['ytmusic_id']}")

    print(f"\n  {len(entries) + 1}. Sync all")
    print(f"  0. Exit\n")

    while True:
        choice = input("Select playlist to sync: ").strip()

        if choice == "0":
            print("Bye!")
            sys.exit(0)

        if choice == str(len(entries) + 1):
            print("\nSyncing all playlists...")
            for sid, info in entries:
                print(f"\n{'='*50}")
                sync(sid, info["ytmusic_id"], sp_dc)
            print("\nAll done!")
            sys.exit(0)

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(entries):
                sid, info = entries[idx]
                print(f"\nSyncing: {info['name']}")
                sync(sid, info["ytmusic_id"], sp_dc)
                print("\nDone!")
                sys.exit(0)
            else:
                print("Invalid choice, try again.")
        except ValueError:
            print("Enter a number, try again.")


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
