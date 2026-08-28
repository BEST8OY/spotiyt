"""Sync Studio tab module for SpotiYT."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, ProgressBar, RichLog, Select, Switch, TabPane


class SyncStudioTab(TabPane):
    """Sync Studio Tab Pane for 1-off playlist pairing, testing, and telemetry."""

    def __init__(self) -> None:
        super().__init__("Sync Studio", id="tab-sync")

    def compose(self) -> ComposeResult:
        with Vertical(classes="form-panel"):
            yield Label("⚡ Sync Workbench & Parameters", classes="form-section-title")
            with Horizontal(classes="form-row"):
                yield Label("Select Playlist:", classes="form-label")
                yield Select[str]([], prompt="Choose registered playlist...", id="sync-select-playlist")

            with Horizontal(classes="form-row"):
                yield Label("Spotify Playlist ID / URL:", classes="form-label")
                yield Input(placeholder="e.g. 37i9dQZF1E8MCNiiTgwMk8", id="sync-input-spotify-id")

            with Horizontal(classes="form-row"):
                yield Label("YouTube Music Playlist ID:", classes="form-label")
                yield Input(placeholder="e.g. PLrAl5G2L...", id="sync-input-ytmusic-id")

            with Vertical(classes="switch-group"):
                with Horizontal(classes="switch-row"):
                    yield Switch(value=False, id="sync-switch-preserve")
                    yield Label("Preserve extra YouTube tracks", classes="switch-label")
                with Horizontal(classes="switch-row"):
                    yield Switch(value=False, id="sync-switch-personalized")
                    yield Label("Use personalized token (sp_dc)", classes="switch-label")
                with Horizontal(classes="switch-row"):
                    yield Switch(value=False, id="sync-switch-dry")
                    yield Label("Dry Run (Preview changes)", classes="switch-label")

            with Horizontal(classes="toolbar"):
                yield Button("Start Sync", variant="primary", id="btn-sync-start")
                yield Button("Preview Dry Run", variant="default", id="btn-sync-preview")
                yield Button("Clear Log", variant="default", id="btn-sync-clear")
                yield Button("Reset Inputs", variant="default", id="btn-sync-reset")

        with Vertical(classes="output-panel"):
            yield Label("📊 Live Telemetry & Log Console", classes="form-section-title")
            yield ProgressBar(total=100, show_eta=False, id="sync-progress")
            yield RichLog(highlight=True, markup=True, id="sync-log")
