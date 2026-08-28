"""Spotify Importer tab module for SpotiYT."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, ProgressBar, RichLog, Select, Switch, TabPane

from spotiyt.config import EXPORTS_DIR


class SpotifyImporterTab(TabPane):
    """Spotify Importer Tab Pane for importing public or private Spotify playlists."""

    def __init__(self) -> None:
        super().__init__("Spotify Importer", id="tab-import")

    def compose(self) -> ComposeResult:
        with Vertical(classes="form-panel"):
            with Horizontal(classes="form-row"):
                yield Label("Spotify Playlist Link/ID:", classes="form-label")
                yield Input(placeholder="Paste https://open.spotify.com/playlist/... or ID", id="import-input-url")

            with Horizontal(classes="form-row"):
                yield Label("Authentication Mode:", classes="form-label")
                yield Select[str](
                    [
                        ("Standard (Public Playlists - Anonymous)", "standard"),
                        ("Personalized (Using sp_dc Cookie)", "personalized"),
                    ],
                    value="standard",
                    allow_blank=False,
                    id="import-select-auth",
                )

            with Horizontal(classes="form-row"):
                yield Label("Export Directory:", classes="form-label")
                yield Input(value=str(EXPORTS_DIR), id="import-input-output")

            with Horizontal(classes="switch-row"):
                yield Switch(value=False, id="import-switch-dry")
                yield Label("Dry Run (Export CSV only, skip YouTube Music creation)", classes="switch-label")

            with Horizontal(classes="toolbar"):
                yield Button("Start Import", variant="primary", id="btn-import-start", classes="btn-primary")
                yield Button("Clear Log", variant="default", id="btn-import-clear", classes="btn-secondary")

        with Vertical(classes="output-panel"):
            yield ProgressBar(total=100, show_eta=False, id="import-progress")
            yield RichLog(highlight=True, markup=True, id="import-log")
