import json
import sys
from pathlib import Path
from typing import Any

from ytmusicapi import YTMusic

from spotiyt.config import REGISTRY_FILE, ensure_data_dir
from spotiyt.matching import (
    _artist_ratio,
    join_artist_names,
    normalize_title,
    strip_parens,
    word_ratio,
)
from spotiyt.spotify import fetch_playlist, get_token, parse_spotify_items
from spotiyt.ui import (
    Table,
    console,
    print_banner,
    print_error,
    print_info,
    print_success,
    print_summary_table,
    print_warning,
)
from spotiyt.ytmusic import (
    add_in_batches,
    deduplicate,
    get_ytmusic_client,
    remove_in_batches,
    search_tracks,
)


def load_registry(path_obj: Path | None = None) -> dict[str, dict[str, str]]:
    ensure_data_dir()
    path = Path(path_obj) if path_obj else REGISTRY_FILE
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    return {}


def save_registry(data: dict[str, dict[str, str]], path_obj: Path | None = None):
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

    table = Table(
        title="Registered Playlists", border_style="cyan", title_style="bold cyan", header_style="bold magenta"
    )
    table.add_column("#", style="dim", width=4)
    table.add_column("Playlist Name", style="bold white")
    table.add_column("Spotify ID", style="cyan")
    table.add_column("YouTube Music ID", style="green")

    for idx, (sid, info) in enumerate(data.items(), 1):
        table.add_row(str(idx), info.get("name", "Unknown"), sid, info.get("ytmusic_id", ""))

    console.print(table)


def get_yt_playlist(ytm: YTMusic, playlist_id: str) -> tuple[str, list[dict[str, str]]]:
    playlist = ytm.get_playlist(playlist_id, limit=None)
    tracks = []
    for t in playlist.get("tracks", []):
        if t and t.get("videoId"):
            tracks.append(
                {
                    "videoId": t["videoId"],
                    "setVideoId": t.get("setVideoId"),
                    "title": t.get("title", ""),
                    "artists": join_artist_names(t.get("artists", [])),
                }
            )
    return playlist.get("title", ""), tracks


def find_unmatched(
    spotify_tracks: list[dict[str, str]], yt_tracks: list[dict[str, str]]
) -> tuple[list[dict[str, str]], list[str], list[dict[str, str]]]:
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
            if title_score >= 0.5 and artist_ok and title_score > best_score:
                best_score = title_score
                best_i = i
        if best_i is not None:
            matched_ids.append(yt_tracks[best_i]["videoId"])
            yt_used.add(best_i)
        else:
            unmatched_spotify.append(st)

    unmatched_yt = [t for i, t in enumerate(yt_tracks) if i not in yt_used]
    return unmatched_spotify, matched_ids, unmatched_yt


def _sync_log(level: str, msg: str, log_cb: Any | None = None):
    if log_cb:
        log_cb(level, msg)
    else:
        if level == "success":
            print_success(msg)
        elif level == "error":
            print_error(msg)
        elif level == "warning":
            print_warning(msg)
        elif level == "info":
            print_info(msg)
        else:
            console.print(msg)


def sync(
    spotify_id: str,
    ytmusic_id: str,
    preserve: bool = False,
    personalized: bool = False,
    dry_run: bool = False,
    log_cb: Any | None = None,
    progress_cb: Any | None = None,
) -> dict[str, Any]:
    if not log_cb:
        print_banner("Playlist Sync", f"Spotify: {spotify_id} ➔ YouTube Music: {ytmusic_id}")
    else:
        log_cb("info", f"Starting Playlist Sync: Spotify ({spotify_id}) ➔ YouTube Music ({ytmusic_id})")

    ytm = get_ytmusic_client()

    if not log_cb and sys.stdout.isatty():
        status_ctx = console.status("[bold cyan]Fetching Spotify playlist...")
        status_ctx.__enter__()
    else:
        status_ctx = None
        if log_cb:
            log_cb("info", "Fetching Spotify playlist metadata...")

    try:
        token = get_token(personalized)
        name, items = fetch_playlist(token, spotify_id, log_cb=log_cb, progress_cb=progress_cb)
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    _sync_log("info", f"Spotify: [bold cyan]{name}[/bold cyan] ({len(items)} tracks)", log_cb)

    if not log_cb and sys.stdout.isatty():
        status_ctx = console.status("[bold cyan]Fetching YouTube Music playlist...")
        status_ctx.__enter__()
    else:
        status_ctx = None
        if log_cb:
            log_cb("info", "Fetching YouTube Music playlist...")

    try:
        yt_name, yt_tracks = get_yt_playlist(ytm, ytmusic_id)
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    _sync_log("info", f"YouTube Music: [bold cyan]{yt_name}[/bold cyan] ({len(yt_tracks)} tracks)", log_cb)

    spotify_tracks = parse_spotify_items(items)
    unmatched_spotify, matched_ids, unmatched_yt = find_unmatched(spotify_tracks, yt_tracks)

    to_add = []
    unique_videos = []
    not_found = []
    if unmatched_spotify:
        if log_cb or progress_cb:
            found_videos, not_found = search_tracks(ytm, unmatched_spotify, log_cb=log_cb, progress_cb=progress_cb)
        else:
            found_videos, not_found = search_tracks(ytm, unmatched_spotify)
        if not_found:
            _sync_log("warning", f"Unmatched on YouTube Music ({len(not_found)} tracks):", log_cb)
            for t in not_found:
                _sync_log("dim", f"  • [yellow]{t['name']}[/yellow] - {t['artists']}", log_cb)
        if found_videos:
            if log_cb:
                unique_videos, _ = deduplicate(found_videos, log_cb=log_cb)
            else:
                unique_videos, _ = deduplicate(found_videos)
            to_add = [vid for vid, _, _ in unique_videos]
    else:
        _sync_log("success", "All Spotify tracks matched with existing YouTube tracks!", log_cb)

    to_remove = [] if preserve else unmatched_yt

    stats = {
        "Spotify Tracks": len(spotify_tracks),
        "YouTube Tracks": len(yt_tracks),
        "Already Matched": len(matched_ids),
        "Tracks To Add": len(to_add),
        "Tracks To Remove": len(to_remove),
        "Preserve Mode": "[bold green]ON[/bold green]" if preserve else "[dim]OFF[/dim]",
        "Dry Run": "[bold yellow]YES[/bold yellow]" if dry_run else "[dim]NO[/dim]",
    }

    if not log_cb:
        print_summary_table(f"Sync Plan: {name}", stats)
    else:
        _sync_log(
            "info",
            f"Sync Plan for '{name}': Spotify: {len(spotify_tracks)}, YT: {len(yt_tracks)}, Matched: {len(matched_ids)}, To Add: {len(to_add)}, To Remove: {len(to_remove)}",
            log_cb,
        )

    result_summary = {
        "spotify_name": name,
        "yt_name": yt_name,
        "spotify_tracks_count": len(spotify_tracks),
        "yt_tracks_count": len(yt_tracks),
        "matched_count": len(matched_ids),
        "to_add_count": len(to_add),
        "to_remove_count": len(to_remove),
        "to_add_items": unique_videos,
        "to_remove_items": to_remove,
        "not_found_items": not_found,
        "dry_run": dry_run,
        "preserve": preserve,
        "added": 0,
        "failed": 0,
        "removed": 0,
    }

    if dry_run:
        if to_add:
            _sync_log("info", f"Tracks to add ({len(to_add)}):", log_cb)
            for _, track_name, artists in unique_videos:
                _sync_log("dim", f"  • [green]{track_name}[/green] - {artists}", log_cb)
        if to_remove:
            _sync_log("warning", f"Tracks to remove ({len(to_remove)}):", log_cb)
            for t in to_remove:
                _sync_log("dim", f"  • [red]{t['title']}[/red] - {t['artists']}", log_cb)
        _sync_log("info", "Dry run complete. No modifications were made to the playlist.", log_cb)
        return result_summary

    if to_remove:
        _sync_log("warning", f"Removing {len(to_remove)} track(s) no longer in Spotify playlist:", log_cb)
        for t in to_remove:
            _sync_log("dim", f"  • [red]{t['title']}[/red] - {t['artists']}", log_cb)
        remove_entries = []
        for t in to_remove:
            entry = {"videoId": t["videoId"]}
            if t.get("setVideoId"):
                entry["setVideoId"] = t["setVideoId"]
            remove_entries.append(entry)
        if log_cb or progress_cb:
            removed_count = remove_in_batches(ytm, ytmusic_id, remove_entries, log_cb=log_cb, progress_cb=progress_cb)
        else:
            removed_count = remove_in_batches(ytm, ytmusic_id, remove_entries)
        result_summary["removed"] = removed_count

    if to_add:
        _sync_log("info", f"Adding {len(to_add)} missing track(s):", log_cb)
        for _, track_name, artists in unique_videos:
            _sync_log("dim", f"  • [green]{track_name}[/green] - {artists}", log_cb)
        if log_cb or progress_cb:
            added, failed = add_in_batches(ytm, ytmusic_id, to_add, log_cb=log_cb, progress_cb=progress_cb)
        else:
            added, failed = add_in_batches(ytm, ytmusic_id, to_add)
        _sync_log("success", f"Added: {added}, Failed: {failed}", log_cb)
        result_summary["added"] = added
        result_summary["failed"] = failed

    if not log_cb:
        console.print(
            f"\n[bold green]Playlist URL:[/bold green] https://music.youtube.com/playlist?list={ytmusic_id}\n"
        )
    else:
        _sync_log("success", f"Playlist URL: https://music.youtube.com/playlist?list={ytmusic_id}", log_cb)

    return result_summary
