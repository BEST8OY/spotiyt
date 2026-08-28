"""Modal dialogs for the SpotiYT Textual application."""

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, ProgressBar, RichLog, Static

from spotiyt.ui import extract_spotify_id


class ConfirmModal(ModalScreen[bool]):
    """Modal dialog for confirming user actions."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "confirm", "Confirm"),
    ]

    def __init__(
        self,
        title: str = "Are you sure?",
        message: str = "This action cannot be undone.",
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
        is_danger: bool = False,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.dialog_title = title
        self.dialog_message = message
        self.confirm_label = confirm_label
        self.cancel_label = cancel_label
        self.is_danger = is_danger

    def compose(self) -> ComposeResult:
        with Container(classes="modal-dialog"):
            yield Label(self.dialog_title, classes="modal-title")
            yield Static(self.dialog_message, classes="modal-body")
            with Horizontal(classes="modal-buttons"):
                confirm_btn_class = "btn-danger" if self.is_danger else "btn-primary"
                yield Button(
                    self.confirm_label,
                    variant="error" if self.is_danger else "primary",
                    id="btn-confirm",
                    classes=confirm_btn_class,
                )
                yield Button(self.cancel_label, variant="default", id="btn-cancel", classes="btn-secondary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class EditPlaylistModal(ModalScreen[dict[str, str] | None]):
    """Modal for creating or modifying a registered playlist mapping."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        title: str = "Register Playlist Mapping",
        name: str = "",
        spotify_id: str = "",
        ytmusic_id: str = "",
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(id=id, classes=classes)
        self.dialog_title = title
        self.initial_name = name
        self.initial_spotify_id = spotify_id
        self.initial_ytmusic_id = ytmusic_id

    def compose(self) -> ComposeResult:
        with Container(classes="modal-dialog"):
            yield Label(self.dialog_title, classes="modal-title")
            with Vertical(classes="form-panel"):
                yield Label("Playlist Name:", classes="stat-title")
                yield Input(value=self.initial_name, placeholder="e.g. My Favorites", id="input-name")

                yield Label("Spotify Playlist URL or ID:", classes="stat-title")
                yield Input(
                    value=self.initial_spotify_id,
                    placeholder="https://open.spotify.com/playlist/... or raw ID",
                    id="input-spotify-id",
                )

                yield Label("YouTube Music Playlist ID:", classes="stat-title")
                yield Input(value=self.initial_ytmusic_id, placeholder="e.g. PLrAl5G2...", id="input-ytmusic-id")

            yield Label("", id="lbl-status", classes="stat-value red")

            with Horizontal(classes="modal-buttons"):
                yield Button("Save Mapping", variant="primary", id="btn-save", classes="btn-primary")
                yield Button("Cancel", variant="default", id="btn-cancel", classes="btn-secondary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            name = self.query_one("#input-name", Input).value.strip()
            raw_sid = self.query_one("#input-spotify-id", Input).value.strip()
            ytid = self.query_one("#input-ytmusic-id", Input).value.strip()
            status_lbl = self.query_one("#lbl-status", Label)

            if not name:
                status_lbl.update("Playlist name cannot be empty.")
                return

            sid = extract_spotify_id(raw_sid)
            if not sid:
                status_lbl.update("Invalid Spotify Playlist URL or ID.")
                return

            if not ytid:
                status_lbl.update("YouTube Music playlist ID cannot be empty.")
                return

            self.dismiss(
                {
                    "name": name,
                    "spotify_id": sid,
                    "ytmusic_id": ytid,
                }
            )
        else:
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DryRunModal(ModalScreen[None]):
    """Modal to review track diff in dry-run mode."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
        Binding("enter", "dismiss_modal", "Close"),
    ]

    def __init__(
        self,
        summary: dict[str, Any],
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(id=id, classes=classes)
        self.summary = summary

    def compose(self) -> ComposeResult:
        with Container(classes="modal-large"):
            pl_name = self.summary.get("spotify_name", "Playlist")
            yield Label(f"Dry Run Preview: {pl_name}", classes="modal-title")

            with Horizontal(classes="stats-container"):
                with Container(classes="stat-card"):
                    yield Label("Spotify Tracks", classes="stat-title")
                    yield Label(str(self.summary.get("spotify_tracks_count", 0)), classes="stat-value")
                with Container(classes="stat-card"):
                    yield Label("Already Matched", classes="stat-title")
                    yield Label(str(self.summary.get("matched_count", 0)), classes="stat-value green")
                with Container(classes="stat-card"):
                    yield Label("To Add", classes="stat-title")
                    yield Label(str(self.summary.get("to_add_count", 0)), classes="stat-value green")
                with Container(classes="stat-card"):
                    yield Label("To Remove", classes="stat-title")
                    yield Label(str(self.summary.get("to_remove_count", 0)), classes="stat-value red")

            with Container(classes="table-container"):
                yield DataTable(id="diff-table")

            with Horizontal(classes="modal-buttons"):
                yield Button("Close Preview", variant="primary", id="btn-close", classes="btn-primary")

    def on_mount(self) -> None:
        table = self.query_one("#diff-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Action", "Track Name", "Artists")

        to_add = self.summary.get("to_add_items", [])
        for _, name, artists in to_add:
            table.add_row("[bold green]+ ADD[/bold green]", name, artists)

        to_remove = self.summary.get("to_remove_items", [])
        for t in to_remove:
            table.add_row("[bold red]- REMOVE[/bold red]", t.get("title", ""), t.get("artists", ""))

        not_found = self.summary.get("not_found_items", [])
        for t in not_found:
            table.add_row("[bold yellow]? NOT FOUND[/bold yellow]", t.get("name", ""), t.get("artists", ""))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class LiveSyncModal(ModalScreen[None]):
    """Modal displaying live synchronization progress, stage status, and streaming logs."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
    ]

    def __init__(
        self,
        title: str = "Synchronizing Playlist",
        subtitle: str = "Initializing sync engine...",
        id: str | None = None,
        classes: str | None = None,
    ):
        super().__init__(id=id, classes=classes)
        self.dialog_title = title
        self.initial_subtitle = subtitle
        self.is_finished = False

    def compose(self) -> ComposeResult:
        with Container(classes="modal-sync modal-large"):
            yield Label(self.dialog_title, id="sync-modal-title", classes="modal-title")
            yield Label(self.initial_subtitle, id="sync-modal-status", classes="sync-modal-subtitle")
            yield ProgressBar(total=100, show_eta=False, id="sync-modal-progress")
            yield RichLog(highlight=True, markup=True, id="sync-modal-log")
            with Horizontal(classes="modal-buttons"):
                yield Button(
                    "Run in Background",
                    variant="default",
                    id="btn-sync-modal-bg",
                    classes="btn-secondary",
                )
                yield Button(
                    "Close",
                    variant="primary",
                    id="btn-sync-modal-close",
                    classes="btn-primary",
                )

    def on_mount(self) -> None:
        try:
            close_btn = self.query_one("#btn-sync-modal-close", Button)
            close_btn.display = False
        except Exception:
            pass

    def write_log(self, text: str) -> None:
        try:
            log_widget = self.query_one("#sync-modal-log", RichLog)
            log_widget.write(text)
        except Exception:
            pass

    def update_progress(self, current: int, total: int, description: str = "") -> None:
        try:
            if total > 0:
                bar = self.query_one("#sync-modal-progress", ProgressBar)
                bar.update(total=total, progress=current)
            if description:
                lbl = self.query_one("#sync-modal-status", Label)
                lbl.update(description)
        except Exception:
            pass

    def set_complete(self, summary_msg: str, is_success: bool = True) -> None:
        self.is_finished = True
        try:
            lbl = self.query_one("#sync-modal-status", Label)
            color = "green" if is_success else "red"
            lbl.update(f"[bold {color}]{summary_msg}[/bold {color}]")

            bar = self.query_one("#sync-modal-progress", ProgressBar)
            bar.update(total=100, progress=100)

            bg_btn = self.query_one("#btn-sync-modal-bg", Button)
            bg_btn.display = False

            close_btn = self.query_one("#btn-sync-modal-close", Button)
            close_btn.display = True
            close_btn.focus()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in ("btn-sync-modal-bg", "btn-sync-modal-close"):
            self.dismiss(None)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
