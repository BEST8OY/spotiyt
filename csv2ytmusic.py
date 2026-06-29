#!/usr/bin/env python3
import sys

from ytmusic_utils import import_to_ytmusic


def main():
    if len(sys.argv) < 2:
        print("Usage: python csv2ytmusic.py <csv_file> [playlist_name]")
        print("CSV must have columns: track_name, artists (optional: album_name)")
        sys.exit(1)

    csv_file = sys.argv[1]
    playlist_name = sys.argv[2] if len(sys.argv) > 2 else csv_file.replace(".csv", "").replace("_", " ")

    import_to_ytmusic(csv_file, playlist_name)


if __name__ == "__main__":
    main()
