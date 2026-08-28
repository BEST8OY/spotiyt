"""Dashboard tab module for SpotiYT."""

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Label, Switch, TabPane


class DashboardTab(TabPane):
    """Dashboard Tab Pane for viewing and managing registered playlists."""

    def __init__(self) -> None:
        super().__init__("Dashboard", id="tab-dashboard")

    def compose(self) -> ComposeResult:
        with Container(classes="table-container"):
            yield DataTable(id="table-playlists")

        with Vertical(classes="sync-options-bar"):
            with Horizontal(classes="switch-row"):
                yield Switch(value=False, id="dash-switch-preserve")
                yield Label("Preserve extra YouTube tracks", classes="switch-label")
            with Horizontal(classes="switch-row"):
                yield Switch(value=False, id="dash-switch-personalized")
                yield Label("Use personalized token (sp_dc)", classes="switch-label")

        with Horizontal(classes="toolbar"):
            yield Button("Sync Selected", variant="primary", id="btn-dash-sync")
            yield Button("Dry Run Selected", variant="default", id="btn-dash-dry")
            yield Button("Sync All", variant="primary", id="btn-dash-sync-all")
            yield Button("Dry Run All", variant="default", id="btn-dash-dry-all")
            yield Button("+ Add Mapping", variant="default", id="btn-dash-add")
            yield Button("Edit Selected", variant="default", id="btn-dash-edit")
            yield Button("Delete Selected", variant="error", id="btn-dash-del")
            yield Button("Delete All", variant="error", id="btn-dash-del-all")
