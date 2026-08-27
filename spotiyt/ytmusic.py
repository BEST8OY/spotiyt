import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

from ytmusicapi import YTMusic

from spotiyt.matching import (
    normalize_title, strip_version, strip_parens, strip_album_edition,
    build_query, word_ratio, _split_artists, _artist_ratio, join_artist_names,
    _album_matches, match_score
)
from spotiyt.ui import (
    console, create_progress, print_success, print_error,
    print_warning, print_info, print_summary_table
)

AUTH_JSON = "auth.json"


def get_ytmusic_client(auth_file: str = AUTH_JSON) -> YTMusic:
    if not Path(auth_file).exists():
        print_error(f"YouTube Music credentials file [yellow]{auth_file}[/yellow] not found.")
        print_info("Run [cyan]python -m spotiyt auth[/cyan] or [cyan]python refresh_yt_auth.py[/cyan] to generate auth.json from cookies.")
        sys.exit(1)
    return YTMusic(auth_file)


def _search_album_fallback(ytm: YTMusic, track: Dict[str, Any], threshold: float = 0.6) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, float]]]:
    album_name = track.get('album', '')
    if not album_name:
        return None, None, None

    artists_list = _split_artists(track['artists'])
    primary_artist = artists_list[0][1] if artists_list else track['artists']
    clean_album = strip_album_edition(album_name)
    query = f"{primary_artist} {clean_album}".strip()
    try:
        album_results = ytm.search(query, filter="albums", limit=5)
    except Exception:
        return None, None, None

    track_artists = track['artists']
    candidates = []

    for album in album_results:
        browse_id = album.get('browseId')
        if not browse_id:
            continue

        album_title = album.get('title', '')
        album_artist = album.get('artist', '') or ''
        title_match = word_ratio(strip_album_edition(album_name), album_title)
        artist_match = _artist_ratio(track_artists, album_artist) if album_artist else title_match
        if title_match < threshold and artist_match < threshold:
            continue

        try:
            album_data = ytm.get_album(browse_id)
        except Exception:
            continue

        tracks = album_data.get('tracks', [])
        track_name = normalize_title(track['name'])
        track_base = normalize_title(strip_parens(track['name']))

        for t in tracks:
            t_title = normalize_title(t.get('title', ''))
            t_base = normalize_title(strip_parens(t.get('title', '')))
            t_artists_str = join_artist_names(t.get('artists', []))
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
    artists = join_artist_names(best_match.get('artists', []))
    score = {"title": best_title, "artist": best_artist}
    return best_match['videoId'], f"{best_match['title']} - {artists}", score


def _search_artist_fallback(ytm: YTMusic, track: Dict[str, Any], threshold: float = 0.6) -> Tuple[Optional[str], Optional[str]]:
    artist_tuples = _split_artists(track['artists'])
    if not artist_tuples:
        return None, None

    track_name = normalize_title(track['name'])
    track_base = normalize_title(strip_parens(track['name']))
    track_artists = track['artists']
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

        channel_id = artist_results[0].get('browseId')
        if not channel_id:
            continue

        try:
            artist_data = ytm.get_artist(channel_id)
        except Exception:
            continue

        for section in ('albums', 'singles'):
            section_data = artist_data.get(section, {})
            browse_id = section_data.get('browseId')
            params = section_data.get('params')
            if not browse_id or not params:
                continue

            try:
                items = ytm.get_artist_albums(browse_id, params, limit=50)
            except Exception:
                continue

            for item in items:
                item_browse = item.get('browseId')
                if not item_browse:
                    continue

                try:
                    album_data = ytm.get_album(item_browse)
                except Exception:
                    continue

                for t in album_data.get('tracks', []):
                    t_title = normalize_title(t.get('title', ''))
                    t_base = normalize_title(strip_parens(t.get('title', '')))
                    title_score = max(word_ratio(track_name, t_title), word_ratio(track_base, t_base))
                    if title_score < 0.5:
                        continue
                    t_artists = join_artist_names(t.get('artists', []))
                    artist_score = _artist_ratio(track_artists, t_artists)
                    if artist_score < 0.5:
                        continue
                    candidates.append((title_score, artist_score, t))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_title, best_artist, best_match = candidates[0]
    artists = join_artist_names(best_match.get('artists', []))
    return best_match['videoId'], f"{best_match['title']} - {artists}"


def search_track(ytm: YTMusic, track: Dict[str, Any], threshold: float = 0.6) -> Tuple[Optional[str], Optional[str]]:
    track_name = track['name']
    track_artists = track.get('artists', '')

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
                track_title = normalize_title(track['name'])
                result_title = normalize_title(best_match.get('title', ''))
                title_exact = word_ratio(track_title, result_title) >= 0.9
                base_exact = word_ratio(
                    normalize_title(strip_parens(track['name'])),
                    normalize_title(strip_parens(best_match.get('title', '')))
                ) >= 0.9

                if _album_matches(track, best_match) and (title_exact or base_exact):
                    artists = join_artist_names(best_match.get('artists', []))
                    return best_match['videoId'], f"{best_match['title']} - {artists} [high]"

                result_vid, result_info, scores = _search_album_fallback(ytm, track, threshold)
                if result_vid and scores:
                    level = "high" if scores["title"] >= 0.9 and scores["artist"] >= 0.9 else "medium"
                    return result_vid, f"{result_info} [{level}]"

                if title_exact or base_exact:
                    artists = join_artist_names(best_match.get('artists', []))
                    return best_match['videoId'], f"{best_match['title']} - {artists} [medium]"

                if _album_matches(track, best_match):
                    artists = join_artist_names(best_match.get('artists', []))
                    return best_match['videoId'], f"{best_match['title']} - {artists} [medium]"

                artists = join_artist_names(best_match.get('artists', []))
                return best_match['videoId'], f"{best_match['title']} - {artists} [medium]"

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
                artists = join_artist_names(best_match.get('artists', []))
                return best_match['videoId'], f"{best_match['title']} - {artists} [medium]"

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


def search_tracks(ytm: YTMusic, tracks: List[Dict[str, Any]], threads: int = 4) -> Tuple[List[Tuple[str, str, str]], List[Dict[str, Any]]]:
    def worker(args):
        i, track = args
        vid, info = search_track(ytm, track)
        return i, vid, info

    results = []
    not_found = []
    total = len(tracks)

    if sys.stdout.isatty():
        with create_progress() as progress:
            task = progress.add_task(f"[bold cyan]Searching {total} tracks...", total=total)
            with ThreadPoolExecutor(max_workers=threads) as pool:
                futures = {pool.submit(worker, (i, t)): i for i, t in enumerate(tracks)}
                for f in as_completed(futures):
                    i, vid, info = f.result()
                    if vid:
                        results.append((i, vid, tracks[i]['name'], tracks[i]['artists']))
                    else:
                        not_found.append(tracks[i])
                    progress.advance(task)
    else:
        with ThreadPoolExecutor(max_workers=threads) as pool:
            futures = {pool.submit(worker, (i, t)): i for i, t in enumerate(tracks)}
            for f in as_completed(futures):
                i, vid, info = f.result()
                if vid:
                    results.append((i, vid, tracks[i]['name'], tracks[i]['artists']))
                else:
                    not_found.append(tracks[i])

    results.sort(key=lambda x: x[0])
    found_videos = [(vid, name, artists) for _, vid, name, artists in results]
    return found_videos, not_found


def deduplicate(found_videos: List[Tuple[str, str, str]]) -> Tuple[List[Tuple[str, str, str]], List[Tuple[str, str]]]:
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
        print_warning(f"Deduplicated {len(duplicates)} repeated track(s):")
        for name, artists in duplicates:
            console.print(f"  [dim]•[/dim] {name} - {artists}")
    return unique, duplicates


def add_in_batches(ytm: YTMusic, playlist_id: str, video_ids: List[str], batch_size: int = 25) -> Tuple[int, int]:
    added = 0
    failed = 0
    total = len(video_ids)
    if not total:
        return 0, 0
    with create_progress() as progress:
        task = progress.add_task(f"[bold green]Adding {total} tracks...", total=total)
        for i in range(0, total, batch_size):
            batch = video_ids[i:i + batch_size]
            try:
                ytm.add_playlist_items(playlist_id, batch, duplicates=True)
                added += len(batch)
            except Exception as e:
                failed += len(batch)
                print_error(f"Failed batch at {i}: {e}")
            progress.advance(task, advance=len(batch))
            time.sleep(0.5)
    return added, failed


def remove_in_batches(ytm: YTMusic, playlist_id: str, entries: List[Dict[str, str]], batch_size: int = 25) -> int:
    removed = 0
    total = len(entries)
    if not total:
        return 0
    with create_progress() as progress:
        task = progress.add_task(f"[bold red]Removing {total} extra tracks...", total=total)
        for i in range(0, total, batch_size):
            batch = entries[i:i + batch_size]
            try:
                ytm.remove_playlist_items(playlist_id, batch)
                removed += len(batch)
            except Exception as e:
                print_error(f"Failed removing batch: {e}")
            progress.advance(task, advance=len(batch))
    print_success(f"Removed {removed}/{total} track(s)")
    return removed


def verify_playlist(ytm: YTMusic, playlist_id: str, expected_ids: List[str]) -> set:
    with console.status("[bold cyan]Verifying playlist contents on YouTube Music..."):
        time.sleep(2)
        playlist = ytm.get_playlist(playlist_id, limit=None)
        tracks_data = playlist.get("tracks", [])
        actual_ids = set(item["videoId"] for item in tracks_data if item and "videoId" in item)
        expected_set = set(expected_ids)
        missing = expected_set - actual_ids

    if missing:
        print_warning(f"Verification: Expected {len(expected_set)}, Actual {len(actual_ids)}, Missing {len(missing)}")
    else:
        print_success(f"Verification passed: All {len(expected_set)} tracks verified in playlist")
    return missing


def save_not_found(csv_file: str, not_found: List[Dict[str, Any]]):
    if not_found:
        not_found_file = csv_file.replace(".csv", "_not_found.csv")
        with open(not_found_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["track_name", "artists"])
            for t in not_found:
                writer.writerow([t["name"], t["artists"]])
        print_info(f"Unmatched tracks saved to [yellow]{not_found_file}[/yellow]")


def save_dropped(csv_file: str, tracks: List[Dict[str, Any]], video_ids: List[str], missing_ids: set):
    if missing_ids:
        missing_file = csv_file.replace(".csv", "_dropped.csv")
        with open(missing_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["track_name", "artists", "video_id"])
            for i, vid in enumerate(video_ids):
                if vid in missing_ids:
                    writer.writerow([tracks[i]["name"], tracks[i]["artists"], vid])
        print_warning(f"Dropped tracks saved to [yellow]{missing_file}[/yellow]")


def load_tracks(csv_file: str) -> List[Dict[str, str]]:
    tracks = []
    with open(csv_file) as f:
        for row in csv.DictReader(f):
            tracks.append({
                "name": row.get("track_name", ""),
                "artists": row.get("artists", ""),
                "album": row.get("album_name", ""),
            })
    return tracks


def import_to_ytmusic(csv_file: str, playlist_name: str, description: str = "Imported from CSV") -> str:
    ytm = get_ytmusic_client()

    tracks = load_tracks(csv_file)
    print_info(f"Loaded [bold]{len(tracks)}[/bold] tracks from [cyan]{csv_file}[/cyan]")

    with console.status(f"[bold cyan]Creating YouTube Music playlist: {playlist_name}..."):
        playlist_id = ytm.create_playlist(title=playlist_name, description=description)
    print_success(f"Created playlist: [bold cyan]{playlist_name}[/bold cyan] (ID: {playlist_id})")

    found_videos, not_found = search_tracks(ytm, tracks)
    print_info(f"Matched [bold green]{len(found_videos)}[/bold green] / [bold]{len(tracks)}[/bold] tracks on YouTube Music")

    save_not_found(csv_file, not_found)

    added, failed = 0, 0
    if found_videos:
        unique, _ = deduplicate(found_videos)
        unique_ids = [v[0] for v in unique]
        added, failed = add_in_batches(ytm, playlist_id, unique_ids)

        missing = verify_playlist(ytm, playlist_id, unique_ids)
        save_dropped(csv_file, tracks, [v[0] for v in found_videos], missing)

    print_summary_table("Import Summary", {
        "Playlist Name": playlist_name,
        "Total CSV Tracks": len(tracks),
        "Found on YouTube": len(found_videos),
        "Not Found": len(not_found),
        "Added to Playlist": added,
        "Failed Additions": failed,
    })

    console.print(f"\n[bold green]Playlist URL:[/bold green] https://music.youtube.com/playlist?list={playlist_id}\n")
    return playlist_id
