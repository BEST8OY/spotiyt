#!/usr/bin/env python3
import sys
from ytmusicapi import YTMusic

from ytmusic_utils import (
    AUTH_JSON, add_in_batches, deduplicate, load_tracks,
    save_dropped, save_not_found, search_tracks, verify_playlist,
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python csv2ytmusic.py <csv_file> [playlist_name]")
        print("CSV must have columns: track_name, artists (optional: album_name)")
        sys.exit(1)

    csv_file = sys.argv[1]
    playlist_name = sys.argv[2] if len(sys.argv) > 2 else csv_file.replace(".csv", "").replace("_", " ")

    ytm = YTMusic(AUTH_JSON)

    tracks = load_tracks(csv_file)
    print(f"Loaded {len(tracks)} tracks")

    playlist_id = ytm.create_playlist(title=playlist_name, description="Imported from CSV")
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


if __name__ == "__main__":
    main()
