import json
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from ytmusicapi import YTMusic

from spotiyt.matching import (
    normalize_title, strip_parens, word_ratio, _artist_ratio, join_artist_names
)
from spotiyt.spotify import get_token, fetch_playlist, parse_spotify_items
from spotiyt.ytmusic import (
    get_ytmusic_client, search_tracks, add_in_batches, remove_in_batches
)
from spotiyt.ui import (
    console, CursesMenu, print_banner, print_success, print_error,
    print_warning, print_info, print_summary_table, Table
)
from spotiyt.config import REGISTRY_FILE, ensure_data_dir


def load_registry(path_obj: Optional[Path] = None) -> Dict[str, Dict[str, str]]:
    ensure_data_dir()
    path = Path(path_obj) if path_obj else REGISTRY_FILE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def save_registry(data: Dict[str, Dict[str, str]], path_obj: Optional[Path] = None):
    ensure_data_dir()
    path = Path(path_obj) if path_obj else REGISTRY_FILE
    path.write_text(json.dumps(data, indent=2) + "\n")


def register_playlist(spotify_id: str, ytmusic_id: str, name: str):
    data = load_registry()
    data[spotify_id] = {
        "ytmusic_id": ytmusic_id,
        "name": name,
    }
    save_registry(data)


def list_registered_playlists():
    data = load_registry()
    if not data:
        print_warning("No playlists registered yet in playlists.json.")
        return

    table = Table(title="Registered Playlists", border_style="cyan", title_style="bold cyan", header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Playlist Name", style="bold white")
    table.add_column("Spotify ID", style="cyan")
    table.add_column("YouTube Music ID", style="green")

    for idx, (sid, info) in enumerate(data.items(), 1):
        table.add_row(str(idx), info.get("name", "Unknown"), sid, info.get("ytmusic_id", ""))

    console.print(table)


def get_yt_playlist(ytm: YTMusic, playlist_id: str) -> Tuple[str, List[Dict[str, str]]]:
    playlist = ytm.get_playlist(playlist_id, limit=None)
    tracks = []
    for t in playlist.get("tracks", []):
        if t and t.get("videoId"):
            tracks.append({
                "videoId": t["videoId"],
                "setVideoId": t.get("setVideoId"),
                "title": t.get("title", ""),
                "artists": join_artist_names(t.get("artists", [])),
            })
    return playlist.get("title", ""), tracks


def find_unmatched(spotify_tracks: List[Dict[str, str]], yt_tracks: List[Dict[str, str]]) -> Tuple[List[Dict[str, str]], List[str], List[Dict[str, str]]]:
    yt_used = set()
    unmatched_spotify = []
    matched_ids = []

    for st in spotify_tracks:
        s_title = normalize_title(st["name"])
        s_base = normalize_title(strip_parens(st["name"]))
        best_i = None
        best_score = 0.0
        for i, yt_info in enumerate(yt_tracks):
            if i in yt_used:
                continue
            yt_title = normalize_title(yt_info["title"])
            yt_base = normalize_title(strip_parens(yt_info["title"]))
            title_score = max(word_ratio(s_title, yt_title), word_ratio(s_base, yt_base))
            artist_ok = _artist_ratio(st["artists"], yt_info["artists"]) >= 0.5
            if title_score >= 0.5 and artist_ok:
                if title_score > best_score:
                    best_score = title_score
                    best_i = i
        if best_i is not None:
            matched_ids.append(yt_tracks[best_i]["videoId"])
            yt_used.add(best_i)
        else:
            unmatched_spotify.append(st)

    unmatched_yt = [t for i, t in enumerate(yt_tracks) if i not in yt_used]
    return unmatched_spotify, matched_ids, unmatched_yt


def sync(spotify_id: str, ytmusic_id: str, preserve: bool = False, personalized: bool = False, dry_run: bool = False):
    print_banner("Playlist Sync", f"Spotify: {spotify_id} ➔ YouTube Music: {ytmusic_id}")
    ytm = get_ytmusic_client()

    with console.status("[bold cyan]Fetching Spotify playlist..."):
        token = get_token(personalized)
        name, items = fetch_playlist(token, spotify_id)
    print_info(f"Spotify: [bold cyan]{name}[/bold cyan] ({len(items)} tracks)")

    with console.status("[bold cyan]Fetching YouTube Music playlist..."):
        yt_name, yt_tracks = get_yt_playlist(ytm, ytmusic_id)
    print_info(f"YouTube Music: [bold cyan]{yt_name}[/bold cyan] ({len(yt_tracks)} tracks)")

    spotify_tracks = parse_spotify_items(items)
    unmatched_spotify, matched_ids, unmatched_yt = find_unmatched(spotify_tracks, yt_tracks)

    to_add = []
    if unmatched_spotify:
        found_videos, not_found = search_tracks(ytm, unmatched_spotify)
        to_add = [vid for vid, _, _ in found_videos]
        if not_found:
            print_warning(f"Unmatched on YouTube Music ({len(not_found)} tracks):")
            for t in not_found:
                console.print(f"  [dim]•[/dim] [yellow]{t['name']}[/yellow] - {t['artists']}")
    else:
        print_success("All Spotify tracks matched with existing YouTube tracks!")

    to_remove = [] if preserve else unmatched_yt

    print_summary_table(f"Sync Plan: {name}", {
        "Spotify Tracks": len(spotify_tracks),
        "YouTube Tracks": len(yt_tracks),
        "Already Matched": len(matched_ids),
        "Tracks To Add": len(to_add),
        "Tracks To Remove": len(to_remove),
        "Preserve Mode": "[bold green]ON[/bold green]" if preserve else "[dim]OFF[/dim]",
        "Dry Run": "[bold yellow]YES[/bold yellow]" if dry_run else "[dim]NO[/dim]",
    })

    if dry_run:
        print_info("Dry run complete. No modifications were made to the playlist.")
        return

    if to_remove:
        print_warning(f"Removing {len(to_remove)} track(s) no longer in Spotify playlist:")
        for t in to_remove:
            console.print(f"  [dim]•[/dim] [red]{t['title']}[/red] - {t['artists']}")
        remove_entries = []
        for t in to_remove:
            entry = {"videoId": t["videoId"]}
            if t.get("setVideoId"):
                entry["setVideoId"] = t["setVideoId"]
            remove_entries.append(entry)
        remove_in_batches(ytm, ytmusic_id, remove_entries)

    if to_add:
        print_info("Adding missing tracks...")
        added, failed = add_in_batches(ytm, ytmusic_id, to_add)
        print_success(f"Added: {added}, Failed: {failed}")

    console.print(f"\n[bold green]Playlist URL:[/bold green] https://music.youtube.com/playlist?list={ytmusic_id}\n")


def build_sync_menu(entries: List[Tuple[str, Dict[str, Any]]], preserve: bool, personalized: bool) -> List[Dict[str, Any]]:
    items = []
    for sid, info in entries:
        items.append({
            "label": f"{info['name']}",
            "badge": "READY",
            "sid": sid
        })
    items.append({"separator": True})
    items.append({
        "label": "Preserve extra YouTube tracks",
        "badge": "ON" if preserve else "OFF",
        "action": "preserve"
    })
    items.append({
        "label": "Personalized Spotify token",
        "badge": "ON" if personalized else "OFF",
        "action": "personalized"
    })
    items.append({"label": "Sync all registered playlists", "badge": "ALL", "action": "sync_all"})
    items.append({"label": "Delete all registered playlists", "badge": "DANGER", "action": "delete_all"})
    items.append({"label": "Exit", "action": "exit"})
    return items


def interactive_sync_menu(preserve: bool = False, personalized: bool = False):
    data = load_registry()

    if not data:
        print_banner("Playlist Sync", "Interactive Manager")
        print_warning("No playlists registered yet.")
        print_info("Run [cyan]spotiyt import[/cyan] first to export and register playlists.")
        sys.exit(0)

    entries = list(data.items())
    items = build_sync_menu(entries, preserve, personalized)

    while True:
        menu = CursesMenu(items, title="Spotify to YouTube Music - Playlist Sync", subtitle="Select a playlist to sync or configure options")
        choice = menu.run()

        if choice == -1:
            console.print("\n[dim]Exited.[/dim]")
            sys.exit(0)

        item = items[choice]
        action = item.get("action")

        if action == "exit":
            console.print("\n[dim]Goodbye![/dim]")
            sys.exit(0)

        if action == "preserve":
            preserve = not preserve
            items = build_sync_menu(entries, preserve, personalized)
            continue

        if action == "personalized":
            personalized = not personalized
            items = build_sync_menu(entries, preserve, personalized)
            continue

        if action == "sync_all":
            console.print("\n[bold cyan]Syncing all registered playlists...[/bold cyan]\n")
            for sid, info in entries:
                console.rule(f"[bold cyan]{info['name']}[/bold cyan]")
                sync(sid, info["ytmusic_id"], preserve, personalized)
            print_success("All registered playlists synchronized successfully!")
            sys.exit(0)

        if action == "delete_all":
            confirm_menu = CursesMenu([
                {"label": "Yes, delete ALL playlists from registry", "badge": "DELETE"},
                {"label": "Cancel / Go back", "badge": "BACK"},
            ], title="Confirm Deletion", subtitle="Are you sure you want to remove all playlists from the registry?")
            if confirm_menu.run() == 0:
                save_registry({})
                print_success(f"Removed all {len(entries)} playlist(s) from registry.")
                sys.exit(0)
            continue

        sid = item["sid"]
        info = data[sid]

        sub_menu = CursesMenu([
            {"label": f"Sync: {info['name']}", "badge": "SYNC"},
            {"label": f"Preview changes (Dry Run)", "badge": "DRY RUN"},
            {"label": f"Delete from registry", "badge": "DELETE"},
            {"label": "Back to main menu", "badge": "BACK"},
        ], title=f"Manage: {info['name']}", subtitle=f"Spotify ID: {sid} ➔ YTM: {info['ytmusic_id']}")
        sub_choice = sub_menu.run()

        if sub_choice == 0:
            console.clear()
            sync(sid, info["ytmusic_id"], preserve, personalized, dry_run=False)
            print_success("Sync complete!")
            sys.exit(0)
        elif sub_choice == 1:
            console.clear()
            sync(sid, info["ytmusic_id"], preserve, personalized, dry_run=True)
            input("\nPress Enter to return to menu...")
        elif sub_choice == 2:
            data.pop(sid)
            save_registry(data)
            print_success(f"Removed '{info['name']}' from registry.")
            entries = list(data.items())
            if not entries:
                print_warning("All playlists removed from registry.")
                sys.exit(0)
            items = build_sync_menu(entries, preserve, personalized)
