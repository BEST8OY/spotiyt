# Spotify to YouTube Music

Export Spotify playlists and import them into YouTube Music.

## Features

- Export Spotify playlists via GraphQL (17 metadata columns)
- Search tracks on YouTube Music with smart fuzzy matching (title + artist + album)
- Deduplicate tracks before import
- Batch add with verification
- Generates `_not_found.csv` and `_dropped.csv` for missing tracks
- Interactive sync with arrow-key navigation (add missing, remove extras)
- Delete playlists from registry via menu

## Prerequisites

- Python 3 with `pyotp`, `requests`, `ytmusicapi`
- Your Spotify `sp_dc` cookie (from browser DevTools)
- YouTube Music browser cookies exported as JSON

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

Get your `sp_dc` cookie from browser DevTools (Application → Cookies → open.spotify.com → sp_dc) and save it:

```bash
echo -n "AQAg4DWr..." > sp_dc.txt
```

The `sp_dc` cookie is required for `--personalized` mode. Without it, anonymous mode still works.

The `sp_dc` cookie is required. Additional cookies (`sp_key`, `sp_t`, etc.) enable personalized playlists (Made for You, Daily Mix, etc.) with the `--personalized` flag.

### 3. YouTube Music auth (one-time)

Export cookies from https://music.youtube.com in JSON format (e.g., using "EditThisCookie" or "Cookie-Editor" extension) and save as `ytm-cookies.json`:

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

For **personalized playlists** (Made for You, Daily Mix, etc.), add `--personalized`:

```bash
python spotify2ytmusic.py --personalized "37i9dQZF1E8MCNiiTgwMk8"
```

Interactive mode (no args):

```bash
python spotify2ytmusic.py
```

Shows a menu to toggle personalized mode and enter playlist IDs.

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

### Sync existing YouTube Music playlist with Spotify

Interactive mode (no args):

```bash
python sync_ytmusic.py
```

Shows registered playlists and lets you pick which to sync. Arrow keys to navigate, Enter to select.

Options in the menu:
- **Sync** -- Add missing tracks, remove extras
- **Delete** -- Remove playlist from registry
- **Preserve extras** -- Toggle to keep extra YouTube tracks instead of removing them
- **Personalized** -- Toggle to use full cookies for personalized playlists
- **Sync all** -- Sync every registered playlist
- **Delete all** -- Remove all playlists from registry (with confirmation)

Direct mode:

```bash
python sync_ytmusic.py <spotify_playlist_id> <ytmusic_playlist_id>
```

With `--preserve` flag to keep extra YouTube tracks:

```bash
python sync_ytmusic.py --preserve <spotify_playlist_id> <ytmusic_playlist_id>
```

With `--personalized` flag for personalized playlists:

```bash
python sync_ytmusic.py --personalized <spotify_playlist_id> <ytmusic_playlist_id>
```

List registered playlists:

```bash
python sync_ytmusic.py --list
```

### Finding Playlist ID

From `https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8`, the ID is `37i9dQZF1E8MCNiiTgwMk8`.

## Project Structure

| File | Description |
|------|-------------|
| `spotify2ytmusic.py` | Full pipeline: Spotify export -> CSV -> YouTube Music import (interactive + personalized) |
| `csv2ytmusic.py` | Import existing CSV to YouTube Music |
| `sync_ytmusic.py` | Sync existing YouTube Music playlist with Spotify |
| `ytmusic_utils.py` | Shared functions (search, dedup, batch add, verification) |
| `refresh_yt_auth.py` | Refresh YouTube Music auth from cookies |

## How It Works

### Initial import (`spotify2ytmusic.py`)

1. Authenticates with Spotify via TOTP + `sp_dc` cookie from `sp_dc.txt` (or anonymous token if not personalized)
2. Fetches playlist via GraphQL (pathfinder API)
3. Saves full CSV (17 columns)
4. Searches each track on YouTube Music (4 parallel threads)
5. Deduplicates video IDs, showing which tracks are duplicates
6. Adds tracks in batches of 25 with `duplicates=True`
7. Verifies playlist contents after adding
8. Saves `_not_found.csv` and `_dropped.csv` for any missing tracks
9. Registers playlist mapping in `playlists.json`

### Sync (`sync_ytmusic.py`)

1. Fetches both Spotify and YouTube Music playlists
2. Matches tracks by title + artist (substring comparison)
3. Only searches unmatched tracks on YouTube Music
4. Adds missing tracks, removes extras
5. Prints each track being added/removed

## Output Files

- `<output>.csv` -- Full export with all metadata
- `<output>_not_found.csv` -- Tracks not found on YouTube Music
- `<output>_dropped.csv` -- Tracks dropped during playlist add
- `playlists.json` -- Registry of Spotify -> YouTube Music playlist mappings

During import, duplicate tracks are listed:

```
Removed 3 duplicate(s):
  - Bohemian Rhapsody - Queen
  - Stairway to Heaven - Led Zeppelin
```

## Refreshing YouTube Music Cookies

When auth expires:

1. Export fresh cookies from browser -> `ytm-cookies.json`
2. Run `python refresh_yt_auth.py`

## Troubleshooting

### GQL error 400: "Query string is not allowed"

The `PLAYLIST_HASH` is outdated. This SHA256 hash identifies the persisted GraphQL query Spotify expects.

**Source:** [hetu_spotify_gql_client](https://github.com/sonic-liberation/hetu_spotify_gql_client/blob/32f3a26808cb5a991723b22d220820dd9ebfa6ce/lib/assets/hetu/playlist.ht)

This file lives at a pinned commit (`32f3a26`) used by the [spotube-plugin-spotify](https://github.com/sonic-liberation/spotube-plugin-spotify) submodule. The `spotify-gql-client` main branch no longer uses this approach (it uses REST instead of GraphQL persisted queries).

Look for `sha256Hash` in the `fetchPlaylist` operation's `extensions.persistedQuery` block. Update `PLAYLIST_HASH` in `spotify2ytmusic.py`.

## License

MIT
