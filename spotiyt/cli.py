import argparse
import sys
from pathlib import Path
from typing import List, Optional

from spotiyt.ui import (
    console, CursesMenu, print_banner, print_success, print_error,
    print_warning, print_info, extract_spotify_id
)
from spotiyt.spotify import (
    fetch_playlist, get_token, save_csv, sanitize_filename
)
from spotiyt.ytmusic import (
    import_to_ytmusic
)
from spotiyt.sync import (
    sync, interactive_sync_menu, list_registered_playlists,
    load_registry, register_playlist
)
from spotiyt.auth import refresh_from_cookies_json
from spotiyt.config import EXPORTS_DIR, COOKIES_JSON, AUTH_JSON, ensure_data_dir


def process_spotify_import(raw_id_or_url: str, personalized: bool = False, output_dir: Optional[str] = None, dry_run: bool = False):
    ensure_data_dir()
    playlist_id = extract_spotify_id(raw_id_or_url)
    if not playlist_id:
        print_error(f"Could not extract a valid Spotify Playlist ID from: [yellow]{raw_id_or_url}[/yellow]")
        return

    console.rule(f"[bold cyan]Processing Playlist: {playlist_id}[/bold cyan]")
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
    register_playlist(playlist_id, yt_id, name)


def prompt_playlist_ids_interactive() -> List[str]:
    console.print("\n[bold cyan]Enter Spotify Playlist URL(s) or ID(s):[/bold cyan]")
    console.print("[dim]Paste Spotify links (e.g., https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8)[/dim]")
    console.print("[dim]Press Enter on an empty line when finished.[/dim]\n")

    ids = []
    while True:
        try:
            line = input("  ➔ Playlist URL/ID: ").strip()
            if not line:
                break
            extracted = extract_spotify_id(line)
            if extracted:
                ids.append(extracted)
                print_success(f"Added ID: [cyan]{extracted}[/cyan]")
            else:
                print_warning(f"Invalid format: '{line}'. Please paste a valid Spotify playlist URL or ID.")
        except (EOFError, KeyboardInterrupt):
            break
    return ids


def interactive_main_dashboard():
    items = [
        {"label": "Sync Existing Playlists", "badge": "SYNC", "action": "sync"},
        {"label": "Import Spotify Playlist(s)", "badge": "IMPORT", "action": "import"},
        {"label": "Import from CSV File", "badge": "CSV", "action": "csv"},
        {"separator": True},
        {"label": "View Registered Playlists", "badge": "VIEW", "action": "view"},
        {"label": "Refresh YouTube Music Auth", "badge": "AUTH", "action": "auth"},
        {"label": "Exit", "action": "exit"},
    ]

    while True:
        menu = CursesMenu(items, title="Spotify to YouTube Music (spotiyt)", subtitle="Select an action to proceed")
        choice = menu.run()

        if choice == -1 or items[choice].get("action") == "exit":
            console.print("\n[dim]Goodbye![/dim]")
            sys.exit(0)

        action = items[choice].get("action")

        if action == "sync":
            interactive_sync_menu()
            continue

        if action == "view":
            console.clear()
            print_banner("Registry", "Saved Spotify ➔ YouTube Music mappings")
            list_registered_playlists()
            input("\nPress Enter to return to menu...")
            continue

        if action == "import":
            console.clear()
            print_banner("Spotify Importer", "Enter playlist links or IDs")
            playlist_ids = prompt_playlist_ids_interactive()
            if not playlist_ids:
                print_warning("No playlists entered.")
                time_sleep = 1
                continue

            for pid in playlist_ids:
                process_spotify_import(pid, personalized=False)

            input("\nImport complete! Press Enter to return to menu...")
            continue

        if action == "csv":
            console.clear()
            print_banner("CSV Importer", "Import tracks from CSV file")
            csv_path = input("  ➔ Enter path to CSV file: ").strip()
            if not csv_path or not Path(csv_path).exists():
                print_error("File not found or empty.")
            else:
                pname = input("  ➔ Playlist name (optional, press Enter to default): ").strip()
                pname = pname if pname else Path(csv_path).stem.replace("_", " ").title()
                import_to_ytmusic(csv_path, pname)
            input("\nPress Enter to return to menu...")
            continue

        if action == "auth":
            console.clear()
            print_banner("YouTube Music Auth", "Generate auth.json from ytm-cookies.json")
            refresh_from_cookies_json()
            input("\nPress Enter to return to menu...")
            continue


def main():
    parser = argparse.ArgumentParser(
        prog="spotiyt",
        description="Spotify to YouTube Music playlist exporter, importer, and synchronizer.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

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
    import_parser.add_argument("-p", "--personalized", action="store_true", help="Use personalized Spotify credentials (sp_dc)")
    import_parser.add_argument("-n", "--dry-run", action="store_true", help="Export to CSV only without importing to YouTube Music")
    import_parser.add_argument("-o", "--output-dir", help="Directory to save exported CSV files")

    # Subcommand: csv
    csv_parser = subparsers.add_parser("csv", help="Import a CSV file to YouTube Music")
    csv_parser.add_argument("csv_file", help="Path to CSV file")
    csv_parser.add_argument("playlist_name", nargs="?", help="Name for the YouTube Music playlist")
    csv_parser.add_argument("-d", "--description", default="Imported from CSV", help="Playlist description")

    # Subcommand: auth
    auth_parser = subparsers.add_parser("auth", help="Generate auth.json from cookies JSON")
    auth_parser.add_argument("cookies_file", nargs="?", default=str(COOKIES_JSON), help=f"Path to exported cookies JSON (default: {COOKIES_JSON})")
    auth_parser.add_argument("-o", "--output", default=str(AUTH_JSON), help=f"Path to output auth.json (default: {AUTH_JSON})")

    # Subcommand: list
    subparsers.add_parser("list", help="List registered playlist mappings")

    args = parser.parse_args()

    if not args.command:
        try:
            interactive_main_dashboard()
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
                for sid, info in data.items():
                    console.rule(f"[bold cyan]{info['name']}[/bold cyan]")
                    sync(sid, info["ytmusic_id"], args.preserve, args.personalized, args.dry_run)
                print_success("Completed sync for all playlists.")
            elif args.spotify_id and args.ytmusic_id:
                sync(args.spotify_id, args.ytmusic_id, args.preserve, args.personalized, args.dry_run)
            else:
                interactive_sync_menu(args.preserve, args.personalized)

        elif args.command == "import":
            if args.playlists:
                for p in args.playlists:
                    process_spotify_import(p, args.personalized, args.output_dir, args.dry_run)
            else:
                prompt_ids = prompt_playlist_ids_interactive()
                for p in prompt_ids:
                    process_spotify_import(p, args.personalized, args.output_dir, args.dry_run)

        elif args.command == "csv":
            csv_path = Path(args.csv_file)
            if not csv_path.exists():
                print_error(f"File not found: [yellow]{args.csv_file}[/yellow]")
                sys.exit(1)
            pname = args.playlist_name if args.playlist_name else csv_path.stem.replace("_", " ").title()
            import_to_ytmusic(str(csv_path), pname, description=args.description)

        elif args.command == "auth":
            refresh_from_cookies_json(args.cookies_file, args.output)

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
