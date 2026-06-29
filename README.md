# Spotify to YouTube Music

Export Spotify playlists and import them into YouTube Music.

## Features

- Export Spotify playlists via GraphQL (17 metadata columns)
- Search tracks on YouTube Music with smart fuzzy matching (title + artist + album)
- Deduplicate tracks before import
- Batch add with verification
- Generates `_not_found.csv` and `_dropped.csv` for missing tracks

## Prerequisites

- Python 3 with `pyotp`, `requests`, `ytmusicapi`
- Your Spotify `sp_dc` cookie (from browser DevTools), saved to `sp_dc.txt`
- YouTube Music cookies (exported as JSON)

## Setup

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Arch Linux (system packages, may be outdated)
sudo pacman -S python-pyotp python-requests python-ytmusicapi
```

### 2. Spotify auth

Save your `sp_dc` cookie value to a file:
```bash
echo -n "AQAg4DWr..." > sp_dc.txt
```

### 3. YouTube Music auth (one-time)

Export cookies from https://music.youtube.com in JSON format (e.g., using "EditThisCookie" or "Cookie-Editor" extension) and save as `cookies.json`:

```bash
python refresh_yt_auth.py
```

This generates `auth.json` used by the import scripts.

## Usage

### Full pipeline (Spotify -> CSV -> YouTube Music)

```bash
python spotify2ytmusic.py <playlist_id> [playlist_id2] ...
```

Example:

```bash
python spotify2ytmusic.py "37i9dQZF1E8MCNiiTgwMk8"
python spotify2ytmusic.py "37i9dQZF1E8MCNiiTgwMk8" "37i9dQZF1DX0XUsuxWHRQd"
```

Output files are named after each playlist: `Zombie_Radio.csv`, `RapCaviar.csv`, etc.

### CSV to YouTube Music only

```bash
python csv2ytmusic.py <csv_file> [playlist_name]
```

Example:

```bash
python csv2ytmusic.py Zombie_Radio.csv "Zombie Radio"
```

CSV must have columns: `track_name`, `artists`. Optional: `album_name` (improves match accuracy).

### Finding Playlist ID

From `https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8`, the ID is `37i9dQZF1E8MCNiiTgwMk8`.

## Project Structure

| File | Description |
|------|-------------|
| `spotify2ytmusic.py` | Full pipeline: Spotify export -> CSV -> YouTube Music import |
| `csv2ytmusic.py` | Import existing CSV to YouTube Music |
| `ytmusic_utils.py` | Shared functions (search, dedup, batch add, verification) |
| `refresh_yt_auth.py` | Refresh YouTube Music auth from cookies |

## How It Works

1. Authenticates with Spotify via TOTP + `sp_dc` cookie
2. Fetches playlist via GraphQL (pathfinder API)
3. Saves full CSV (17 columns)
4. Searches each track on YouTube Music (4 parallel threads)
5. Deduplicates video IDs, showing which tracks are duplicates
6. Adds tracks in batches of 25 with `duplicates=True`
7. Verifies playlist contents after adding
8. Saves `_not_found.csv` and `_dropped.csv` for any missing tracks

## Output Files

- `<output>.csv` -- Full export with all metadata
- `<output>_not_found.csv` -- Tracks not found on YouTube Music
- `<output>_dropped.csv` -- Tracks dropped during playlist add

During import, duplicate tracks are listed:

```
Removed 3 duplicate(s):
  - Bohemian Rhapsody - Queen
  - Stairway to Heaven - Led Zeppelin
```

## Refreshing YouTube Music Cookies

When auth expires:

1. Export fresh cookies from browser -> `cookies.json`
2. Run `python refresh_yt_auth.py`

## Troubleshooting

### GQL error 400: "Query string is not allowed"

The `PLAYLIST_HASH` is outdated. This SHA256 hash identifies the persisted GraphQL query Spotify expects.

**Source:** [hetu_spotify_gql_client](https://github.com/sonic-liberation/hetu_spotify_gql_client/blob/32f3a26808cb5a991723b22d220820dd9ebfa6ce/lib/assets/hetu/playlist.ht)

This file lives at a pinned commit (`32f3a26`) used by the [spotube-plugin-spotify](https://github.com/sonic-liberation/spotube-plugin-spotify) submodule. The `spotify-gql-client` main branch no longer uses this approach (it uses REST instead of GraphQL persisted queries).

Look for `sha256Hash` in the `fetchPlaylist` operation's `extensions.persistedQuery` block. Update `PLAYLIST_HASH` in `spotify2ytmusic.py`.

## License

MIT
