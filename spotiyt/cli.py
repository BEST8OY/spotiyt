import argparse
import sys
from pathlib import Path

from spotiyt.auth import refresh_from_cookies_json
from spotiyt.config import AUTH_JSON, COOKIES_JSON, EXPORTS_DIR, ensure_data_dir
from spotiyt.spotify import fetch_playlist, get_token, sanitize_filename, save_csv
from spotiyt.sync import (
    list_registered_playlists,
    load_registry,
    register_playlist,
    sync,
)
from spotiyt.ui import (
    console,
    extract_spotify_id,
    print_error,
    print_info,
    print_success,
    print_warning,
)
from spotiyt.ytmusic import import_to_ytmusic


def process_spotify_import(
    raw_id_or_url: str, personalized: bool = False, output_dir: str | None = None, dry_run: bool = False
):
    ensure_data_dir()
    playlist_id = extract_spotify_id(raw_id_or_url)
    if not playlist_id:
        print_error(f"Could not extract a valid Spotify Playlist ID from: [yellow]{raw_id_or_url}[/yellow]")
        return

    console.rule(f"[bold cyan]Processing Playlist: {playlist_id}[/bold cyan]")
    try:
        token = get_token(personalized)
        name, items = fetch_playlist(token, playlist_id)

        sanitized = sanitize_filename(name) or playlist_id
        out_dir = Path(output_dir) if output_dir else EXPORTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        output_file = str(out_dir / f"{sanitized}.csv")

        save_csv(name, items, output_file)

        if dry_run:
            print_info("Dry run mode: Skipped YouTube Music playlist creation.")
            return

        yt_id = import_to_ytmusic(output_file, f"{name} (Spotify)", "Imported from Spotify")
        if yt_id:
            register_playlist(playlist_id, yt_id, name)
    except Exception as e:
        print_error(f"Failed to process playlist {playlist_id}: {e}")


def launch_tui():
    from spotiyt.tui import SpotiYTApp

    app = SpotiYTApp()
    app.run()
    app.run()


def main():
    parser = argparse.ArgumentParser(
        prog="spotiyt",
        description="Spotify to YouTube Music playlist exporter, importer, and synchronizer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Subcommand: tui
    subparsers.add_parser("tui", help="Launch interactive Textual TUI dashboard")

    # Subcommand: sync
    sync_parser = subparsers.add_parser("sync", help="Sync Spotify playlist with YouTube Music")
    sync_parser.add_argument("spotify_id", nargs="?", help="Spotify playlist ID or URL")
    sync_parser.add_argument("ytmusic_id", nargs="?", help="YouTube Music playlist ID")
    sync_parser.add_argument("-p", "--preserve", action="store_true", help="Preserve extra tracks in YouTube Music")
    sync_parser.add_argument("--personalized", action="store_true", help="Use personalized Spotify credentials")
    sync_parser.add_argument("-n", "--dry-run", action="store_true", help="Preview changes without modifying playlists")
    sync_parser.add_argument("-l", "--list", action="store_true", help="List registered playlist mappings")
    sync_parser.add_argument("-a", "--all", action="store_true", help="Sync all registered playlists")

    # Subcommand: import
    import_parser = subparsers.add_parser("import", help="Export Spotify playlist and import to YouTube Music")
    import_parser.add_argument("playlists", nargs="*", help="Spotify playlist URLs or IDs")
    import_parser.add_argument(
        "-p", "--personalized", action="store_true", help="Use personalized Spotify credentials (sp_dc)"
    )
    import_parser.add_argument(
        "-n", "--dry-run", action="store_true", help="Export to CSV only without importing to YouTube Music"
    )
    import_parser.add_argument("-o", "--output-dir", help="Directory to save exported CSV files")

    # Subcommand: csv
    csv_parser = subparsers.add_parser("csv", help="Import a CSV file to YouTube Music")
    csv_parser.add_argument("csv_file", help="Path to CSV file")
    csv_parser.add_argument("playlist_name", nargs="?", help="Name for the YouTube Music playlist")
    csv_parser.add_argument("-d", "--description", default="Imported from CSV", help="Playlist description")

    # Subcommand: auth
    auth_parser = subparsers.add_parser("auth", help="Generate auth.json from cookies JSON")
    auth_parser.add_argument(
        "cookies_file",
        nargs="?",
        default=str(COOKIES_JSON),
        help=f"Path to exported cookies JSON (default: {COOKIES_JSON})",
    )
    auth_parser.add_argument(
        "-o", "--output", default=str(AUTH_JSON), help=f"Path to output auth.json (default: {AUTH_JSON})"
    )

    # Subcommand: list
    subparsers.add_parser("list", help="List registered playlist mappings")

    args = parser.parse_args()

    if not args.command or args.command == "tui":
        try:
            launch_tui()
        except KeyboardInterrupt:
            console.print("\n[dim]Process interrupted by user.[/dim]")
            sys.exit(0)
        return

    try:
        if args.command == "sync":
            if args.list:
                list_registered_playlists()
            elif args.all:
                data = load_registry()
                if not data:
                    print_warning("No playlists registered in playlists.json.")
                    return
                success_count = 0
                for sid, info in data.items():
                    console.rule(f"[bold cyan]{info['name']}[/bold cyan]")
                    try:
                        sync(sid, info["ytmusic_id"], args.preserve, args.personalized, args.dry_run)
                        success_count += 1
                    except Exception as e:
                        print_error(f"Failed to sync '{info['name']}': {e}")
                print_success(f"Completed sync for {success_count}/{len(data)} playlists.")
            elif args.spotify_id and args.ytmusic_id:
                sync(args.spotify_id, args.ytmusic_id, args.preserve, args.personalized, args.dry_run)
            else:
                launch_tui()

        elif args.command == "import":
            if args.playlists:
                for p in args.playlists:
                    process_spotify_import(p, args.personalized, args.output_dir, args.dry_run)
            else:
                launch_tui()

        elif args.command == "csv":
            csv_path = Path(args.csv_file)
            if not csv_path.exists():
                print_error(f"File not found: [yellow]{args.csv_file}[/yellow]")
                sys.exit(1)
            pname = args.playlist_name if args.playlist_name else csv_path.stem.replace("_", " ").title()
            import_to_ytmusic(str(csv_path), pname, description=args.description)

        elif args.command == "auth":
            success = refresh_from_cookies_json(args.cookies_file, args.output)
            if not success:
                sys.exit(1)

        elif args.command == "list":
            list_registered_playlists()

    except KeyboardInterrupt:
        console.print("\n[dim]Process interrupted by user.[/dim]")
        sys.exit(0)
    except Exception as e:
        print_error(f"Command failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
