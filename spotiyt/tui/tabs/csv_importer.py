"""CSV Importer tab module for SpotiYT."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, ProgressBar, RichLog, TabPane


class CSVImporterTab(TabPane):
    """CSV Importer Tab Pane for creating YouTube Music playlists from CSV files."""

    def __init__(self) -> None:
        super().__init__("CSV Importer", id="tab-csv")

    def compose(self) -> ComposeResult:
        with Vertical(classes="form-panel"):
            with Horizontal(classes="form-row"):
                yield Label("Path to CSV File:", classes="form-label")
                yield Input(placeholder="/path/to/playlist.csv", id="csv-input-path")

            with Horizontal(classes="form-row"):
                yield Label("Playlist Name (optional):", classes="form-label")
                yield Input(placeholder="Leave empty to use file name", id="csv-input-name")

            with Horizontal(classes="form-row"):
                yield Label("Playlist Description:", classes="form-label")
                yield Input(value="Imported from CSV", id="csv-input-desc")

            with Horizontal(classes="toolbar"):
                yield Button(
                    "Import CSV to YouTube Music", variant="primary", id="btn-csv-start", classes="btn-primary"
                )
                yield Button("Clear Log", variant="default", id="btn-csv-clear", classes="btn-secondary")

        with Vertical(classes="output-panel"):
            yield ProgressBar(total=100, show_eta=False, id="csv-progress")
            yield RichLog(highlight=True, markup=True, id="csv-log")
