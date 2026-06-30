#!/usr/bin/env python3
import csv
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

from ytmusicapi import YTMusic

AUTH_JSON = "auth.json"
REGISTRY = "playlists.json"

VERSION_PATTERNS = [
    r'\s*[-–]\s*(\d{4}\s+)?Remaster(ed)?(\s+Version)?(\s+\d{4})?\s*$',
    r'\s*\((\d{4}\s+)?Remaster(ed)?(\s+Version)?(\s+\d{4})\)\s*$',
    r'\s*\(feat\.\s+.*?\)\s*$',
    r'\s*\(with\s+.*?\)\s*$',
    r'\s+feat\.?\s+\S+.*$',
]

YOUTUBE_NOISE = [
    r'\s*[-–]\s*Official\s+(Video|Audio|Music\s+Video)\s*$',
    r'\s*\(Official\s+(Video|Audio|Music\s+Video)\)\s*$',
    r'\s*\((?:Lyrics|Visualizer|Visualiser)\)\s*$',
]

ALBUM_STRIP_PATTERNS = [
    r'\s*\(.*?(Deluxe|Remaster|Edition|Live|Anniversary).*?\)\s*$',
    r'\s*[-–]\s*(Deluxe|Remaster|Edition|Live|Anniversary).*?$',
]


def clean(s):
    s = s.lower().strip()
    s = re.sub(r'\s*(feat\.|ft\.|featuring)\s*', ' ', s)
    s = s.replace(';', ' ')
    s = s.replace('-', ' ')
    s = s.replace('(', ' ')
    s = s.replace(')', ' ')
    s = s.replace('+', ' ')
    s = s.replace('*', '')
    s = s.replace('&', ' ')
    s = s.replace("'", '')
    s = s.replace('.', '')
    s = re.sub(r'\s*:\s*', ':', s)
    s = re.sub(r'[,]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def strip_version(title):
    for p in VERSION_PATTERNS:
        title = re.sub(p, '', title, flags=re.IGNORECASE)
    for p in YOUTUBE_NOISE:
        title = re.sub(p, '', title, flags=re.IGNORECASE)
    return title.strip()


def strip_parens(title):
    return re.sub(r'\s*\(.*?\)\s*', ' ', title).strip()


def strip_album_edition(album):
    for p in ALBUM_STRIP_PATTERNS:
        album = re.sub(p, '', album, flags=re.IGNORECASE)
    return album.strip()


def build_query(track):
    parts = [track['name'], track['artists']]
    album = strip_album_edition(track.get('album', ''))
    if album:
        parts.append(album)
    return ' '.join(parts)


def word_ratio(s1, s2):
    w1 = s1.split()
    w2 = s2.split()
    if not w1 and not w2:
        return 1.0
    if not w1 or not w2:
        return 0.0
    seq_score = SequenceMatcher(None, w1, w2).ratio()
    s1_set, s2_set = set(w1), set(w2)
    intersection = s1_set & s2_set
    jaccard = len(intersection) / len(s1_set | s2_set) if s1_set | s2_set else 0.0
    return max(seq_score, jaccard)


def _split_artists(s):
    names = re.split(r'\s*[;,/]\s+|\s+&\s+|\s+feat\.?\s+|\s+ft\.?\s+', s.strip())
    return {clean(n) for n in names if n.strip()}


def _artist_ratio(track_artists, result_artists):
    track_names = _split_artists(track_artists)
    result_names = _split_artists(result_artists)
    if not result_names:
        return 0.0
    if not track_names:
        return 0.0
    matched = sum(1 for a in result_names if a in track_names)
    return matched / len(result_names)


def match_score(track, result):
    title_score = word_ratio(
        normalize_title(track['name']),
        normalize_title(result.get('title', ''))
    )

    artist_score = _artist_ratio(
        track['artists'],
        join_artist_names(result.get('artists', []))
    )

    if artist_score < 0.5:
        return 0.0

    if title_score < 0.5:
        return 0.0

    album_score = 1.0
    expected_album = track.get('album', '')
    result_album = (result.get('album') or {}).get('name', '')
    if expected_album and result_album:
        album_score = word_ratio(clean(expected_album), clean(result_album))

    album_weight = 0.3 if title_score >= 0.9 else 0.2
    return title_score * 0.4 + artist_score * 0.3 + album_score * album_weight


def _search_album_fallback(ytm, track, threshold=0.6):
    album_name = track.get('album', '')
    if not album_name:
        return None, None

    primary_artist = re.split(r'\s*[;,/]\s+|\s+&\s+|\s+feat\.?\s+|\s+ft\.?\s+', track['artists'].strip())[0]
    query = f"{primary_artist} {album_name}"
    try:
        album_results = ytm.search(query, filter="albums", limit=5)
    except Exception:
        return None, None

    track_artists = track['artists']
    candidates = []

    for album in album_results:
        browse_id = album.get('browseId')
        if not browse_id:
            continue

        album_title = clean(album.get('title', ''))
        album_artist = album.get('artist', '') or ''
        title_match = word_ratio(clean(album_name), album_title)
        artist_match = _artist_ratio(track_artists, album_artist) if album_artist else title_match
        if title_match < threshold and artist_match < threshold:
            continue

        try:
            album_data = ytm.get_album(browse_id)
        except Exception:
            continue

        tracks = album_data.get('tracks', [])
        track_name = normalize_title(track['name'])

        for t in tracks:
            t_title = normalize_title(t.get('title', ''))
            t_artists_str = join_artist_names(t.get('artists', []))
            title_score = word_ratio(track_name, t_title)
            artist_score = _artist_ratio(track_artists, t_artists_str)
            if artist_score < 0.5:
                continue
            if title_score >= 0.5:
                candidates.append((title_score, artist_score, t))

    if not candidates:
        return None, None

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_title, best_artist, best_match = candidates[0]
    artists = join_artist_names(best_match.get('artists', []))
    score = {"title": best_title, "artist": best_artist}
    return best_match['videoId'], f"{best_match['title']} - {artists}", score


def _album_matches(track, result):
    expected = track.get('album', '')
    if not expected:
        return True
    actual = (result.get('album') or {}).get('name', '')
    if not actual:
        return True
    return word_ratio(clean(expected), clean(actual)) >= 0.5


def _search_artist_fallback(ytm, track, threshold=0.6):
    artist_names = _split_artists(track['artists'])
    if not artist_names:
        return None, []

    track_name = normalize_title(track['name'])
    track_artists = track['artists']
    candidates = []
    searched = set()

    for name in artist_names:
        if name in searched:
            continue
        searched.add(name)

        try:
            artist_results = ytm.search(name, filter="artists", limit=1)
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
                    title_score = word_ratio(track_name, t_title)
                    if title_score < 0.5:
                        continue
                    t_artists = join_artist_names(t.get('artists', []))
                    artist_score = _artist_ratio(track_artists, t_artists)
                    if artist_score < 0.5:
                        continue
                    candidates.append((title_score, artist_score, t))

    if not candidates:
        return None, []

    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_title, best_artist, best_match = candidates[0]
    artists = join_artist_names(best_match.get('artists', []))
    return best_match['videoId'], f"{best_match['title']} - {artists}"


def search_track(ytm, track, threshold=0.6):
    query = build_query(track)
    try:
        results = ytm.search(query, filter="songs", limit=5)
    except Exception:
        results = []

    best_score, best_match = 0.0, None
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

        result = _search_album_fallback(ytm, track, threshold)
        if result[0]:
            vid, info, scores = result
            level = "high" if scores["title"] >= 0.9 and scores["artist"] >= 0.9 else "medium"
            return vid, f"{info} [{level}]"

        if title_exact or base_exact:
            artists = join_artist_names(best_match.get('artists', []))
            return best_match['videoId'], f"{best_match['title']} - {artists} [medium]"

        if _album_matches(track, best_match):
            artists = join_artist_names(best_match.get('artists', []))
            return best_match['videoId'], f"{best_match['title']} - {artists} [medium]"

    result = _search_album_fallback(ytm, track, threshold)
    if result[0]:
        vid, info, scores = result
        level = "high" if scores["title"] >= 0.9 and scores["artist"] >= 0.9 else "medium"
        return vid, f"{info} [{level}]"

    vid, info = _search_artist_fallback(ytm, track, threshold)
    if vid:
        return vid, f"{info} [low]"

    return None, []


def normalize_title(name):
    return clean(strip_version(name))


def join_artist_names(artist_list):
    return ", ".join(a["name"] for a in artist_list)


def get_ytmusic_client():
    return YTMusic(AUTH_JSON)


def parse_spotify_items(items):
    tracks = []
    for item in items:
        if item.get("isLocal"):
            continue
        t = item.get("itemV2", {}).get("data")
        if not t:
            continue
        artists = "; ".join(a["profile"]["name"] for a in t.get("artists", {}).get("items", []))
        album = t.get("albumOfTrack", {})
        tracks.append({
            "name": t["name"],
            "artists": artists,
            "album": album.get("name", ""),
        })
    return tracks


def remove_in_batches(ytm, playlist_id, entries, batch_size=25):
    removed = 0
    for i in range(0, len(entries), batch_size):
        batch = entries[i:i + batch_size]
        try:
            ytm.remove_playlist_items(playlist_id, batch)
            removed += len(batch)
            print(f"  Removed batch {removed}/{len(entries)}")
        except Exception as e:
            print(f"  Failed removing batch: {e}")
    return removed


def import_to_ytmusic(csv_file, playlist_name, description="Imported from CSV"):
    ytm = get_ytmusic_client()

    tracks = load_tracks(csv_file)
    print(f"Loaded {len(tracks)} tracks")

    playlist_id = ytm.create_playlist(title=playlist_name, description=description)
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
    return playlist_id


def load_tracks(csv_file):
    tracks = []
    with open(csv_file) as f:
        for row in csv.DictReader(f):
            tracks.append({
                "name": row.get("track_name", ""),
                "artists": row.get("artists", ""),
                "album": row.get("album_name", ""),
            })
    return tracks


def search_tracks(ytm, tracks, threads=4):
    def worker(args):
        i, track = args
        vid, info = search_track(ytm, track)
        return i, vid, info

    results = []
    not_found = []
    found = 0
    total = len(tracks)
    print(f"Searching {total} tracks ({threads} threads)...")
    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(worker, (i, t)): i for i, t in enumerate(tracks)}
        for f in as_completed(futures):
            i, vid, info = f.result()
            if vid:
                results.append((i, vid, tracks[i]['name'], tracks[i]['artists']))
                found += 1
                print(f"  [{found}/{total}] {info}")
            else:
                not_found.append(tracks[i])
                print(f"  [{i+1}/{total}] NOT FOUND: {tracks[i]['name']} - {tracks[i]['artists']}")

    results.sort(key=lambda x: x[0])
    found_videos = [(vid, name, artists) for _, vid, name, artists in results]
    return found_videos, not_found


def deduplicate(found_videos):
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
        print(f"Removed {len(duplicates)} duplicate(s):")
        for name, artists in duplicates:
            print(f"  - {name} - {artists}")
    return unique, duplicates


def add_in_batches(ytm, playlist_id, video_ids, batch_size=25):
    added = 0
    failed = 0
    for i in range(0, len(video_ids), batch_size):
        batch = video_ids[i:i + batch_size]
        try:
            ytm.add_playlist_items(playlist_id, batch, duplicates=True)
            added += len(batch)
            print(f"  Added batch {added}/{len(video_ids)}")
        except Exception as e:
            failed += len(batch)
            print(f"  Failed batch at {added}: {e}")
        time.sleep(1)
    return added, failed


def verify_playlist(ytm, playlist_id, expected_ids):
    print("\nVerifying playlist...")
    time.sleep(2)
    playlist = ytm.get_playlist(playlist_id, limit=None)
    tracks_data = playlist.get("tracks", [])
    actual_ids = set(item["videoId"] for item in tracks_data if item)
    expected_set = set(expected_ids)
    missing = expected_set - actual_ids
    print(f"Expected: {len(expected_set)}, Actual: {len(actual_ids)}, Missing: {len(missing)}")
    return missing


def save_not_found(csv_file, not_found):
    if not_found:
        not_found_file = csv_file.replace(".csv", "_not_found.csv")
        with open(not_found_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["track_name", "artists"])
            for t in not_found:
                writer.writerow([t["name"], t["artists"]])
        print(f"Not found tracks saved to {not_found_file}")


def save_dropped(csv_file, tracks, video_ids, missing_ids):
    if missing_ids:
        missing_file = csv_file.replace(".csv", "_dropped.csv")
        with open(missing_file, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["track_name", "artists", "video_id"])
            for i, vid in enumerate(video_ids):
                if vid in missing_ids:
                    writer.writerow([tracks[i]["name"], tracks[i]["artists"], vid])


def load_registry():
    path = Path(REGISTRY)
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_registry(data):
    Path(REGISTRY).write_text(json.dumps(data, indent=2) + "\n")


def register_playlist(spotify_id, ytmusic_id, name):
    data = load_registry()
    data[spotify_id] = {
        "ytmusic_id": ytmusic_id,
        "name": name,
    }
    save_registry(data)
