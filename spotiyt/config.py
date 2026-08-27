from pathlib import Path

# Paths configuration
BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data"
EXPORTS_DIR = DATA_DIR / "exports"

AUTH_JSON = DATA_DIR / "auth.json"
COOKIES_JSON = DATA_DIR / "ytm-cookies.json"
SP_DC_FILE = DATA_DIR / "sp_dc.txt"
REGISTRY_FILE = DATA_DIR / "playlists.json"


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
