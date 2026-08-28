# Spotify to YouTube Music (`spotiyt`)

A fast, reliable, and modular Python package + interactive CLI built with **[uv](https://github.com/astral-sh/uv)** to export Spotify playlists and synchronize them with YouTube Music using smart fuzzy matching and automated fallback heuristics.

---

## Key Features

- **Built for UV**: Ultra-fast environment synchronization and execution using `uv`.
- **Unified CLI & Interactive Dashboard**: Launch with `uv run spotiyt` for a full interactive terminal menu, or use dedicated subcommands (`sync`, `import`, `csv`, `auth`, `list`).
- **Clean Data & Secrets Isolation**: All tokens, session cookies, registries, and exported files reside in a dedicated, git-ignored `data/` directory.
- **GraphQL Spotify Export**: Fetches full playlist metadata with 17 attributes without needing official Spotify Developer API keys.
- **Smart Matching Engine**:
  - **Dynamic Artist Matching**: Intelligently handles leading `"The "` prefixes (*The Goo Goo Dolls* $\leftrightarrow$ *Goo Goo Dolls*, *The Beatles* $\leftrightarrow$ *Beatles*), multi-artist delimiters (`;`, `,`, `&`, `feat.`, `ft.`, `x`, `with`), and diacritics/accents (*Beyoncé* $\leftrightarrow$ *Beyonce*).
  - **Version & Noise Stripping**: Cleans remaster tags (`- 2008 Remaster`, `(Remastered 2020)`), anniversary editions, radio edits, and YouTube upload noise (`[Official Audio]`, `(Official Music Video)`, `[Visualizer]`, `(Lyrics)`, `[4K]`).
  - **Multi-Stage Progressive Fallbacks**: Song search $\rightarrow$ video upload search $\rightarrow$ album endpoint search $\rightarrow$ artist catalog browse.
- **Modern Textual TUI Studio**: Full reactive terminal user interface built with **Textual** featuring interactive tabs (Dashboard, Sync Studio, Spotify Importer, CSV Importer, Auth Manager), background worker threads, live progress bars, streaming logs, and modal dialogs.
- **Bidirectional Syncing**: Synchronize existing YouTube Music playlists with Spotify (adds missing tracks, removes extras, with optional `--preserve` and `--dry-run` modes).
- **Batch Processing & Verification**: Imports tracks in batches of 25 with automatic post-import verification, deduplication, and missing-track reporting (`_not_found.csv` and `_dropped.csv`).

---

## Prerequisites

- **[uv](https://docs.astral.sh/uv/)** (installed via `curl -LsSf https://astral.sh/uv/install.sh` or your system package manager)
- **Spotify Cookie**: `sp_dc` cookie (required for personalized playlists like *Discover Weekly*, *Daily Mix*, etc.; anonymous mode works without it).
- **YouTube Music Cookies**: Exported from your browser as JSON to authenticate with YouTube Music.

---

## Quick Start (with UV)

### 1. Clone & Sync Environment

```bash
git clone https://github.com/best8oy/spotiyt.git
cd spotiyt

# Synchronize virtual environment with UV
uv sync
```

### 2. Configure Spotify Authentication

Retrieve your `sp_dc` cookie from browser DevTools:
1. Open [open.spotify.com](https://open.spotify.com) and log in.
2. Open DevTools (`F12` or `Ctrl+Shift+I`) $\rightarrow$ **Application** $\rightarrow$ **Cookies** $\rightarrow$ `https://open.spotify.com`.
3. Copy the value of `sp_dc` and save it to `data/sp_dc.txt`:

```bash
mkdir -p data
echo -n "YOUR_SP_DC_COOKIE_HERE" > data/sp_dc.txt
```

### 3. Configure YouTube Music Authentication

1. Open [music.youtube.com](https://music.youtube.com) and ensure you are logged in.
2. Export your cookies in JSON format using a browser extension (e.g., *Cookie-Editor* or *EditThisCookie*).
3. Save the JSON file as `data/ytm-cookies.json`.
4. Generate `data/auth.json`:

```bash
uv run spotiyt auth
```

---

## Usage Guide

### 1. Interactive Dashboard (Default)
Running `uv run spotiyt` without arguments opens the full interactive terminal menu:

```bash
uv run spotiyt
```

---

### 2. Synchronize Existing Playlists (`spotiyt sync`)
Keeps your YouTube Music playlist in sync with changes made on Spotify.

```bash
# Interactive sync menu
uv run spotiyt sync

# Direct CLI execution
uv run spotiyt sync <spotify_playlist_id_or_url> <ytmusic_playlist_id>

# Preview changes without modifying playlists (Dry Run)
uv run spotiyt sync --dry-run <spotify_id> <ytmusic_id>

# Sync with preserve extras enabled (keeps extra tracks on YouTube Music)
uv run spotiyt sync --preserve <spotify_id> <ytmusic_id>

# Sync all registered playlists
uv run spotiyt sync --all

# List all registered playlists
uv run spotiyt sync --list
```

---

### 3. Import Spotify Playlists (`spotiyt import`)
Exports Spotify playlists to CSV and creates/imports them on YouTube Music.

```bash
# Direct import (supports full Spotify URLs or IDs)
uv run spotiyt import https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8

# Multiple playlists
uv run spotiyt import <playlist_id_1> <playlist_id_2>

# Personalized playlists (Daily Mix, Made for You, etc.)
uv run spotiyt import --personalized <playlist_id>

# Export to CSV only without uploading to YouTube Music
uv run spotiyt import --dry-run <playlist_id>
```

---

### 4. Import from CSV (`spotiyt csv`)
Import an existing CSV file directly into YouTube Music:

```bash
uv run spotiyt csv <path_to_csv_file> [playlist_name]
```

*Example:*
```bash
uv run spotiyt csv data/exports/Zombie_Radio.csv "Zombie Radio"
```

*Required CSV Columns:* `track_name`, `artists` *(Optional: `album_name`)*.

---

### 5. Running Regression Tests
Run the test suite using UV to verify text normalization, title stripping, and artist fuzzy matching:

```bash
uv run python -m unittest discover -s tests
```

---

## How the Matching Engine Works

When matching tracks between Spotify and YouTube Music:

1. **Unicode & Diacritics Normalization**: Converts non-ASCII and accented characters to standard forms (`Mötley Crüe` $\rightarrow$ `motley crue`, `Beyoncé` $\rightarrow$ `beyonce`). Standardizes curly quotes, hyphens, and dashes.
2. **Flexible Artist Matching**:
   - Compares artist tokens with and without leading `"The "` (*"The Goo Goo Dolls"* matches *"Goo Goo Dolls"* with 100% confidence).
   - Splits featured/collaborative artists across conjunctions (`;`, `,`, `&`, `feat.`, `ft.`, `x`, `with`).
   - Grants priority matching to primary artists and recognizes featured artists embedded inside track titles.
3. **Title & Noise Stripping**: Strips version suffixes (`Remastered`, `Radio Edit`, `Live`, `Anniversary Mix`) and upload tags (`Official Music Video`, `Lyric Video`, `HD`, `4K`).
4. **4-Stage Query Fallback**:
   - **Stage 1**: Search under `filter="songs"` with full metadata, then stripped title + primary artist.
   - **Stage 2**: Search under `filter="videos"` to catch tracks only uploaded as official music videos.
   - **Stage 3**: Album lookup fallback via YouTube Music album browsing.
   - **Stage 4**: Artist catalog search fallback.

---

## Project Structure

```
.
├── data/                       # Dedicated data & credential storage (git-ignored)
│   ├── auth.json               # Generated YouTube Music session headers
│   ├── ytm-cookies.json        # Exported browser cookies
│   ├── sp_dc.txt               # Spotify session cookie
│   ├── playlists.json          # Playlist registry mappings
│   └── exports/                # Exported CSV files and dropped/not_found reports
│
├── spotiyt/                    # Main Python package
│   ├── __init__.py             # Package metadata
│   ├── __main__.py             # Module execution entrypoint (`uv run python -m spotiyt`)
│   ├── cli.py                  # Unified CLI dispatcher (sync, import, csv, auth, list, tui)
│   ├── config.py               # Centralized data and credential paths
│   ├── matching.py             # Normalization, title stripping, artist fuzzy matching heuristics
│   ├── spotify.py              # Spotify TOTP token generation, GraphQL fetch, CSV exporter
│   ├── ytmusic.py              # YouTube Music client, progressive search, batch ops, verify
│   ├── sync.py                 # Diff engine, sync workflows, and registry management
│   ├── auth.py                 # Cookie parser and auth.json generator
│   ├── ui.py                   # Centralized Rich terminal engine, progress bars, tables
│   └── tui/                    # Textual Terminal User Interface (Studio)
│       ├── __init__.py         # TUI exports
│       ├── app.py              # Main Textual SpotiYTApp with reactive tabs & workers
│       ├── styles.tcss         # Custom TCSS stylesheet (Spotify/YouTube dark theme)
│       └── screens/
│           └── modals.py       # Modal dialogs (Confirm, Edit Mapping, DryRun Preview)
│
├── tests/                      # Dedicated test suite
│   ├── __init__.py
│   ├── test_auth.py            # Auth & cookie tests
│   ├── test_matching.py        # Automated matching heuristic & regression tests
│   ├── test_sync.py            # Sync logic & deduplication tests
│   ├── test_tui.py             # Asynchronous Textual pilot tests
│   ├── test_ui.py              # UI helper tests
│   └── test_ytmusic.py         # YouTube Music import & search tests
│
├── pyproject.toml              # UV / PEP 621 project configuration
├── uv.lock                     # UV lockfile with pinned dependencies
├── README.md                   # Documentation
├── LICENSE                     # MIT License
└── .gitignore                  # Git ignore rules
```

---

## Output Files

- `data/exports/<playlist_name>.csv`: Complete exported metadata from Spotify.
- `data/exports/<playlist_name>_not_found.csv`: Tracks that could not be matched on YouTube Music (search failure).
- `data/exports/<playlist_name>_dropped.csv`: Tracks found by search but silently rejected by YouTube Music's insertion API (insertion failure).
- `data/playlists.json`: Registry storing mappings between Spotify and YouTube Music playlist IDs.

---

## Troubleshooting

### Cookie Expiration
If YouTube Music API calls fail with authentication errors:
1. Export fresh cookies from [music.youtube.com](https://music.youtube.com) to `data/ytm-cookies.json`.
2. Run `uv run spotiyt auth`.

### Spotify GraphQL Hash Expiration (`PLAYLIST_HASH`)
If Spotify export fails with `400: Query string is not allowed`, the persisted GraphQL query hash in Spotify's backend has rotated:
1. Locate the latest `sha256Hash` for `fetchPlaylist` from [hetu_spotify_gql_client](https://github.com/sonic-liberation/hetu_spotify_gql_client).
2. Update `PLAYLIST_HASH` in [`spotiyt/spotify.py`](file:///home/best8oy/sns/spotiyt/spotify.py).

---

## License

This project is licensed under the [MIT License](file:///home/best8oy/sns/LICENSE).
