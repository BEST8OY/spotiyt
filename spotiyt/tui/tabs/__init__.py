"""Modular tab components for SpotiYT Textual TUI."""

from spotiyt.tui.tabs.auth_settings import AuthSettingsTab
from spotiyt.tui.tabs.csv_importer import CSVImporterTab
from spotiyt.tui.tabs.dashboard import DashboardTab
from spotiyt.tui.tabs.importer import SpotifyImporterTab
from spotiyt.tui.tabs.sync_studio import SyncStudioTab

__all__ = [
    "AuthSettingsTab",
    "CSVImporterTab",
    "DashboardTab",
    "SpotifyImporterTab",
    "SyncStudioTab",
]
