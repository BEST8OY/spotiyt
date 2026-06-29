#!/usr/bin/env python3
import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

AUTH_JSON = "auth.json"
REGISTRY = "playlists.json"

VERSION_PATTERNS = [
    r'\s*[-–]\s*(\d{4}\s+)?Remaster(ed)?(\s+Version)?(\s+\d{4})?\s*$',
    r'\s*\((\d{4}\s+)?Remaster(ed)?(\s+Version)?(\s+\d{4})?\)\s*$',
    r'\s*\(feat\.\s+.*?\)\s*$',
    r'\s*\(with\s+.*?\)\s*$',
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
    s = re.sub(r'[,]+', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def strip_version(title):
    for p in VERSION_PATTERNS:
        title = re.sub(p, '', title, flags=re.IGNORECASE)
    return title.strip()


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
    return SequenceMatcher(None, w1, w2).ratio()


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
        clean(strip_version(track['name'])),
        clean(strip_version(result.get('title', '')))
    )

    artist_score = _artist_ratio(
        track['artists'],
        ', '.join(a['name'] for a in result.get('artists', []))
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

    album_weight = 0.2 if title_score >= 0.9 else 0.1
    return title_score * 0.5 + artist_score * 0.3 + album_score * album_weight


def _search_album_fallback(ytm, track, threshold=0.6):
    album_name = track.get('album', '')
    if not album_name:
        return None, []

    query = f"{track['artists']} {album_name}"
    try:
        album_results = ytm.search(query, filter="albums", limit=5)
    except Exception:
        return None, []

    track_artists = track['artists']

    for album in album_results:
        browse_id = album.get('browseId')
        if not browse_id:
            continue

        album_title = clean(album.get('title', ''))
        album_artist = album.get('artist', '')
        title_match = word_ratio(clean(album_name), album_title)
        artist_match = _artist_ratio(track_artists, album_artist)
        if title_match < threshold and artist_match < threshold:
            continue

        try:
            album_data = ytm.get_album(browse_id)
        except Exception:
            continue

        tracks = album_data.get('tracks', [])
        track_name = clean(strip_version(track['name']))
        best_score = 0.0
        best_match = None

        for t in tracks:
            t_title = clean(strip_version(t.get('title', '')))
            score = word_ratio(track_name, t_title)
            if score > best_score:
                best_score = score
                best_match = t

        if best_match and best_score >= 0.5:
            artists = ', '.join(a['name'] for a in best_match.get('artists', []))
            return best_match['videoId'], f"{best_match['title']} - {artists}"

    return None, []


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

    track_name = clean(strip_version(track['name']))

    for name in list(artist_names)[:2]:
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
                    t_title = clean(strip_version(t.get('title', '')))
                    score = word_ratio(track_name, t_title)
                    if score >= 0.5:
                        artists = ', '.join(a['name'] for a in t.get('artists', []))
                        return t['videoId'], f"{t['title']} - {artists}"

    return None, []


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
        title_exact = word_ratio(
            clean(strip_version(track['name'])),
            clean(strip_version(best_match.get('title', '')))
        ) >= 0.9

        if _album_matches(track, best_match) and title_exact:
            artists = ', '.join(a['name'] for a in best_match.get('artists', []))
            return best_match['videoId'], f"{best_match['title']} - {artists}"

        vid, info = _search_album_fallback(ytm, track, threshold)
        if vid:
            return vid, info

        if _album_matches(track, best_match):
            artists = ', '.join(a['name'] for a in best_match.get('artists', []))
            return best_match['videoId'], f"{best_match['title']} - {artists}"

        artists = ', '.join(a['name'] for a in best_match.get('artists', []))
        return best_match['videoId'], f"{best_match['title']} - {artists}"

    vid, info = _search_album_fallback(ytm, track, threshold)
    if vid:
        return vid, info

    vid, info = _search_artist_fallback(ytm, track, threshold)
    if vid:
        return vid, info

    return None, []


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
