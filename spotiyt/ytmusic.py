import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from ytmusicapi import YTMusic

from spotiyt.config import AUTH_JSON, ensure_data_dir
from spotiyt.matching import (
    _album_matches,
    _artist_ratio,
    _split_artists,
    build_query,
    join_artist_names,
    match_score,
    normalize_title,
    strip_album_edition,
    strip_parens,
    strip_version,
    word_ratio,
)
from spotiyt.ui import (
    console,
    create_progress,
    print_error,
    print_info,
    print_success,
    print_summary_table,
    print_warning,
)


def get_ytmusic_client(auth_file: Path | None = None) -> YTMusic:
    ensure_data_dir()
    target_auth = Path(auth_file) if auth_file else AUTH_JSON
    if not target_auth.exists():
        raise FileNotFoundError(
            f"YouTube Music credentials file '{target_auth}' not found. "
            "Run 'spotiyt auth' to generate auth.json from cookies."
        )
    return YTMusic(str(target_auth))


def _search_album_fallback(
    ytm: YTMusic, track: dict[str, Any], threshold: float = 0.6
) -> tuple[str | None, str | None, dict[str, float] | None]:
    album_name = track.get("album", "")
    if not album_name:
        return None, None, None

    artists_list = _split_artists(track["artists"])
    primary_artist = artists_list[0][1] if artists_list else track["artists"]
    clean_album = strip_album_edition(album_name)
    query = f"{primary_artist} {clean_album}".strip()
    try:
        album_results = ytm.search(query, filter="albums", limit=5)
    except Exception:
        return None, None, None

    track_artists = track["artists"]
    candidates = []

    for album in album_results:
        browse_id = album.get("browseId")
        if not browse_id:
            continue

        album_title = album.get("title", "")
        album_artist = album.get("artist", "") or ""
        title_match = word_ratio(strip_album_edition(album_name), album_title)
        artist_match = _artist_ratio(track_artists, album_artist) if album_artist else title_match
        if title_match < threshold and artist_match < threshold:
            continue

        try:
            album_data = ytm.get_album(browse_id)
        except Exception:
            continue

        tracks = album_data.get("tracks", [])
        track_name = normalize_title(track["name"])
        track_base = normalize_title(strip_parens(track["name"]))

        for t in tracks:
            t_title = normalize_title(t.get("title", ""))
            t_base = normalize_title(strip_parens(t.get("title", "")))
            t_artists_str = join_artist_names(t.get("artists", []))
            title_score = max(word_ratio(track_name, t_title), word_ratio(track_base, t_base))
            artist_score = _artist_ratio(track_artists, t_artists_str)
            if artist_score < 0.5:
                continue
            if title_score >= 0.5:
                candidates.append((title_score, artist_score, t))

    if not candidates:
        return None, None, None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_title, best_artist, best_match = candidates[0]
    artists = join_artist_names(best_match.get("artists", []))
    score = {"title": best_title, "artist": best_artist}
    return best_match["videoId"], f"{best_match['title']} - {artists}", score


def _search_artist_fallback(
    ytm: YTMusic, track: dict[str, Any], threshold: float = 0.6
) -> tuple[str | None, str | None]:
    artist_tuples = _split_artists(track["artists"])
    if not artist_tuples:
        return None, None

    track_name = normalize_title(track["name"])
    track_base = normalize_title(strip_parens(track["name"]))
    track_artists = track["artists"]
    candidates = []
    searched = set()

    for name_clean, name_no_the in artist_tuples:
        search_term = name_no_the or name_clean
        if search_term in searched:
            continue
        searched.add(search_term)

        try:
            artist_results = ytm.search(search_term, filter="artists", limit=1)
        except Exception:
            continue

        if not artist_results:
            continue

        channel_id = artist_results[0].get("browseId")
        if not channel_id:
            continue

        try:
            artist_data = ytm.get_artist(channel_id)
        except Exception:
            continue

        for section in ("albums", "singles"):
            section_data = artist_data.get(section, {})
            browse_id = section_data.get("browseId")
            params = section_data.get("params")
            if not browse_id or not params:
                continue

            try:
                items = ytm.get_artist_albums(browse_id, params, limit=50)
            except Exception:
                continue

            for item in items:
                item_browse = item.get("browseId")
                if not item_browse:
                    continue

                try:
                    album_data = ytm.get_album(item_browse)
                except Exception:
                    continue

                for t in album_data.get("tracks", []):
                    t_title = normalize_title(t.get("title", ""))
                    t_base = normalize_title(strip_parens(t.get("title", "")))
                    title_score = max(word_ratio(track_name, t_title), word_ratio(track_base, t_base))
                    if title_score < 0.5:
                        continue
                    t_artists = join_artist_names(t.get("artists", []))
                    artist_score = _artist_ratio(track_artists, t_artists)
                    if artist_score < 0.5:
                        continue
                    candidates.append((title_score, artist_score, t))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _, _, best_match = candidates[0]
    artists = join_artist_names(best_match.get("artists", []))
    return best_match["videoId"], f"{best_match['title']} - {artists}"


def search_track(ytm: YTMusic, track: dict[str, Any], threshold: float = 0.6) -> tuple[str | None, str | None]:
    track_name = track["name"]
    track_artists = track.get("artists", "")

    artists_list = _split_artists(track_artists)
    primary_artist = artists_list[0][1] if artists_list else track_artists
    clean_title = strip_version(track_name)
    base_title = strip_parens(clean_title)

    queries = []
    q1 = build_query(track)
    if q1:
        queries.append(q1)
    q2 = f"{clean_title} {primary_artist}".strip()
    if q2 and q2 not in queries:
        queries.append(q2)
    if base_title and base_title != clean_title:
        q3 = f"{base_title} {primary_artist}".strip()
        if q3 and q3 not in queries:
            queries.append(q3)

    # 1. Search filter="songs"
    for query in queries:
        try:
            results = ytm.search(query, filter="songs", limit=10)
        except Exception:
            results = []

        if results:
            scored = [(match_score(track, r), r) for r in results]
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_match = scored[0]

            if best_match and best_score >= threshold:
                track_title = normalize_title(track["name"])
                result_title = normalize_title(best_match.get("title", ""))
                title_exact = word_ratio(track_title, result_title) >= 0.9
                base_exact = (
                    word_ratio(
                        normalize_title(strip_parens(track["name"])),
                        normalize_title(strip_parens(best_match.get("title", ""))),
                    )
                    >= 0.9
                )

                if _album_matches(track, best_match) and (title_exact or base_exact):
                    artists = join_artist_names(best_match.get("artists", []))
                    return best_match["videoId"], f"{best_match['title']} - {artists} [high]"

                result_vid, result_info, scores = _search_album_fallback(ytm, track, threshold)
                if result_vid and scores:
                    level = "high" if scores["title"] >= 0.9 and scores["artist"] >= 0.9 else "medium"
                    return result_vid, f"{result_info} [{level}]"

                if title_exact or base_exact:
                    artists = join_artist_names(best_match.get("artists", []))
                    return best_match["videoId"], f"{best_match['title']} - {artists} [medium]"

                if _album_matches(track, best_match):
                    artists = join_artist_names(best_match.get("artists", []))
                    return best_match["videoId"], f"{best_match['title']} - {artists} [medium]"

                artists = join_artist_names(best_match.get("artists", []))
                return best_match["videoId"], f"{best_match['title']} - {artists} [medium]"

    # 2. Search filter="videos"
    for query in queries[:2]:
        try:
            results = ytm.search(query, filter="videos", limit=5)
        except Exception:
            results = []

        if results:
            scored = [(match_score(track, r), r) for r in results]
            scored.sort(key=lambda x: x[0], reverse=True)
            best_score, best_match = scored[0]
            if best_match and best_score >= threshold:
                artists = join_artist_names(best_match.get("artists", []))
                return best_match["videoId"], f"{best_match['title']} - {artists} [medium]"

    # 3. Album fallback
    result_vid, result_info, scores = _search_album_fallback(ytm, track, threshold)
    if result_vid and scores:
        level = "high" if scores["title"] >= 0.9 and scores["artist"] >= 0.9 else "medium"
        return result_vid, f"{result_info} [{level}]"

    # 4. Artist browse fallback
    vid, info = _search_artist_fallback(ytm, track, threshold)
    if vid:
        return vid, f"{info} [low]"

    return None, None


def _log(level: str, msg: str, log_cb: Any | None = None):
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


def search_tracks(
    ytm: YTMusic,
    tracks: list[dict[str, Any]],
    threads: int = 4,
    log_cb: Any | None = None,
    progress_cb: Any | None = None,
) -> tuple[list[tuple[str, str, str]], list[dict[str, Any]]]:
    def worker(args):
        i, track = args
        vid, info = search_track(ytm, track)
        return i, vid, info

    results = []
    not_found = []
    total = len(tracks)
    completed = 0

    use_rich_progress = (progress_cb is None) and sys.stdout.isatty()
    progress_ctx = create_progress() if use_rich_progress else None

    try:
        if progress_ctx:
            progress = progress_ctx.__enter__()
            task = progress.add_task(f"[bold cyan]Searching {total} tracks...", total=total)
        else:
            progress = None
            task = None

        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = {pool.submit(worker, (i, t)): i for i, t in enumerate(tracks)}
            for f in as_completed(futures):
                i, vid, _ = f.result()
                if vid:
                    results.append((i, vid, tracks[i]["name"], tracks[i]["artists"]))
                else:
                    not_found.append(tracks[i])
                completed += 1
                if progress and task:
                    progress.advance(task)
                if progress_cb:
                    progress_cb(completed, total, f"Searching: {completed}/{total}")

    finally:
        if progress_ctx:
            progress_ctx.__exit__(None, None, None)

    results.sort(key=lambda x: x[0])
    found_videos = [(vid, name, artists) for _, vid, name, artists in results]
    return found_videos, not_found


def deduplicate(
    found_videos: list[tuple[str, str, str]], log_cb: Any | None = None
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    seen = set()
    unique = []
    duplicates = []
    for vid, name, artists in found_videos:
        if vid not in seen:
            seen.add(vid)
            unique.append((vid, name, artists))
        else:
            duplicates.append((name, artists))
    if duplicates:
        _log("warning", f"Deduplicated {len(duplicates)} repeated track(s):", log_cb)
        for name, artists in duplicates:
            _log("dim", f"  • {name} - {artists}", log_cb)
    return unique, duplicates


def add_in_batches(
    ytm: YTMusic,
    playlist_id: str,
    video_ids: list[str],
    batch_size: int = 25,
    log_cb: Any | None = None,
    progress_cb: Any | None = None,
) -> tuple[int, int]:
    added = 0
    failed = 0
    total = len(video_ids)
    if not total:
        return 0, 0

    use_rich_progress = (progress_cb is None) and sys.stdout.isatty()
    progress_ctx = create_progress() if use_rich_progress else None

    try:
        if progress_ctx:
            progress = progress_ctx.__enter__()
            task = progress.add_task(f"[bold green]Adding {total} tracks...", total=total)
        else:
            progress = None
            task = None

        for i in range(0, total, batch_size):
            batch = video_ids[i : i + batch_size]
            try:
                ytm.add_playlist_items(playlist_id, batch, duplicates=True)
                added += len(batch)
            except Exception as e:
                failed += len(batch)
                _log("error", f"Failed batch at {i}: {e}", log_cb)
            if progress and task:
                progress.advance(task, advance=len(batch))
            if progress_cb:
                progress_cb(added + failed, total, f"Adding: {added + failed}/{total}")
            time.sleep(0.5)

    finally:
        if progress_ctx:
            progress_ctx.__exit__(None, None, None)

    return added, failed


def remove_in_batches(
    ytm: YTMusic,
    playlist_id: str,
    entries: list[dict[str, str]],
    batch_size: int = 25,
    log_cb: Any | None = None,
    progress_cb: Any | None = None,
) -> int:
    removed = 0
    total = len(entries)
    if not total:
        return 0

    use_rich_progress = (progress_cb is None) and sys.stdout.isatty()
    progress_ctx = create_progress() if use_rich_progress else None

    try:
        if progress_ctx:
            progress = progress_ctx.__enter__()
            task = progress.add_task(f"[bold red]Removing {total} extra tracks...", total=total)
        else:
            progress = None
            task = None

        for i in range(0, total, batch_size):
            batch = entries[i : i + batch_size]
            try:
                ytm.remove_playlist_items(playlist_id, batch)
                removed += len(batch)
            except Exception as e:
                _log("error", f"Failed removing batch: {e}", log_cb)
            if progress and task:
                progress.advance(task, advance=len(batch))
            if progress_cb:
                progress_cb(removed, total, f"Removing: {removed}/{total}")

    finally:
        if progress_ctx:
            progress_ctx.__exit__(None, None, None)

    _log("success", f"Removed {removed}/{total} track(s)", log_cb)
    return removed


def verify_playlist(ytm: YTMusic, playlist_id: str, expected_ids: list[str], log_cb: Any | None = None) -> set:
    if not log_cb and sys.stdout.isatty():
        status_ctx = console.status("[bold cyan]Verifying playlist contents on YouTube Music...")
        status_ctx.__enter__()
    else:
        status_ctx = None
        if log_cb:
            log_cb("info", "Verifying playlist contents on YouTube Music...")

    try:
        time.sleep(2)
        playlist = ytm.get_playlist(playlist_id, limit=None)
        tracks_data = playlist.get("tracks", [])
        actual_ids = {item["videoId"] for item in tracks_data if item and "videoId" in item}
        expected_set = set(expected_ids)
        missing = expected_set - actual_ids
    finally:
        if status_ctx:
            status_ctx.__exit__(None, None, None)

    if missing:
        _log(
            "warning",
            f"Verification: Expected {len(expected_set)}, Actual {len(actual_ids)}, Missing {len(missing)}",
            log_cb,
        )
    else:
        _log("success", f"Verification passed: All {len(expected_set)} tracks verified in playlist", log_cb)
    return missing


def save_not_found(csv_file: str, not_found: list[dict[str, Any]], log_cb: Any | None = None):
    if not_found:
        not_found_file = csv_file.replace(".csv", "_not_found.csv")
        with open(not_found_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["track_name", "artists"])
            for t in not_found:
                writer.writerow([t["name"], t["artists"]])
        _log("info", f"Unmatched tracks saved to [yellow]{not_found_file}[/yellow]", log_cb)


def save_dropped(
    csv_file: str, tracks: list[dict[str, Any]], video_ids: list[str], missing_ids: set, log_cb: Any | None = None
):
    if missing_ids:
        missing_file = csv_file.replace(".csv", "_dropped.csv")
        with open(missing_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["track_name", "artists", "video_id"])
            for i, vid in enumerate(video_ids):
                if vid in missing_ids:
                    writer.writerow([tracks[i]["name"], tracks[i]["artists"], vid])
        _log("warning", f"Dropped tracks saved to [yellow]{missing_file}[/yellow]", log_cb)


def load_tracks(csv_file: str) -> list[dict[str, str]]:
    tracks = []
    with open(csv_file) as f:
        for row in csv.DictReader(f):
            tracks.append(
                {
                    "name": row.get("track_name", ""),
                    "artists": row.get("artists", ""),
                    "album": row.get("album_name", ""),
                }
            )
    return tracks


def import_to_ytmusic(
    csv_file: str,
    playlist_name: str,
    description: str = "Imported from CSV",
    log_cb: Any | None = None,
    progress_cb: Any | None = None,
) -> str:
    ytm = get_ytmusic_client()

    tracks = load_tracks(csv_file)
    if not tracks:
        _log("warning", f"No tracks found in [cyan]{csv_file}[/cyan]. Aborting import.", log_cb)
        return ""

    _log("info", f"Loaded [bold]{len(tracks)}[/bold] tracks from [cyan]{csv_file}[/cyan]", log_cb)

    if log_cb or progress_cb:
        found_videos, not_found = search_tracks(ytm, tracks, log_cb=log_cb, progress_cb=progress_cb)
    else:
        found_videos, not_found = search_tracks(ytm, tracks)
    _log(
        "info",
        f"Matched [bold green]{len(found_videos)}[/bold green] / [bold]{len(tracks)}[/bold] tracks on YouTube Music",
        log_cb,
    )

    if not_found:
        _log("warning", f"Unmatched on YouTube Music ({len(not_found)} tracks):", log_cb)
        for t in not_found:
            _log("dim", f"  • [yellow]{t['name']}[/yellow] - {t['artists']}", log_cb)
        if log_cb:
            save_not_found(csv_file, not_found, log_cb=log_cb)
        else:
            save_not_found(csv_file, not_found)

    if not found_videos:
        _log("error", "No tracks could be matched on YouTube Music. Skipped playlist creation.", log_cb)
        return ""

    if log_cb:
        unique, _ = deduplicate(found_videos, log_cb=log_cb)
    else:
        unique, _ = deduplicate(found_videos)
    unique_ids = [v[0] for v in unique]

    _log("info", f"Creating YouTube Music playlist: [bold cyan]{playlist_name}[/bold cyan]...", log_cb)
    playlist_id = ytm.create_playlist(title=playlist_name, description=description)
    _log("success", f"Created playlist: [bold cyan]{playlist_name}[/bold cyan] (ID: {playlist_id})", log_cb)

    _log("info", f"Adding {len(unique)} track(s) to playlist:", log_cb)
    for _, name, artists in unique:
        _log("dim", f"  • [green]{name}[/green] - {artists}", log_cb)

    if log_cb or progress_cb:
        added, failed = add_in_batches(ytm, playlist_id, unique_ids, log_cb=log_cb, progress_cb=progress_cb)
    else:
        added, failed = add_in_batches(ytm, playlist_id, unique_ids)

    if log_cb:
        missing = verify_playlist(ytm, playlist_id, unique_ids, log_cb=log_cb)
        save_dropped(csv_file, tracks, [v[0] for v in found_videos], missing, log_cb=log_cb)
    else:
        missing = verify_playlist(ytm, playlist_id, unique_ids)
        save_dropped(csv_file, tracks, [v[0] for v in found_videos], missing)

    stats = {
        "Playlist Name": playlist_name,
        "Total CSV Tracks": len(tracks),
        "Found on YouTube": len(found_videos),
        "Not Found": len(not_found),
        "Added to Playlist": added,
        "Failed Additions": failed,
    }
    if not log_cb:
        print_summary_table("Import Summary", stats)
        console.print(
            f"\n[bold green]Playlist URL:[/bold green] https://music.youtube.com/playlist?list={playlist_id}\n"
        )
    else:
        _log(
            "success",
            f"Import complete! Added: {added}/{len(unique)} tracks. Playlist URL: https://music.youtube.com/playlist?list={playlist_id}",
            log_cb,
        )

    return playlist_id
