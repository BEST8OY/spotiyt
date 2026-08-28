"""Main SpotiYT Textual Application."""

from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Select,
    Switch,
    TabbedContent,
)

from spotiyt.auth import refresh_from_cookies_json
from spotiyt.config import (
    AUTH_JSON,
    COOKIES_JSON,
    EXPORTS_DIR,
    SP_DC_FILE,
    ensure_data_dir,
)
from spotiyt.spotify import (
    fetch_playlist,
    get_token,
    sanitize_filename,
    save_csv,
)
from spotiyt.sync import (
    load_registry,
    register_playlist,
    save_registry,
    sync,
)
from spotiyt.tui.screens.modals import ConfirmModal, DryRunModal, EditPlaylistModal, LiveSyncModal
from spotiyt.tui.tabs import (
    AuthSettingsTab,
    CSVImporterTab,
    DashboardTab,
    SpotifyImporterTab,
    SyncStudioTab,
)
from spotiyt.ui import extract_spotify_id
from spotiyt.ytmusic import import_to_ytmusic


class SpotiYTApp(App[None]):
    """Modern Textual application for Spotify to YouTube Music synchronization."""

    TITLE = "spotiyt"
    SUB_TITLE = "Spotify ➔ YouTube Music Sync Studio"
    CSS_PATH = "styles.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("1", "switch_tab('tab-dashboard')", "Dashboard", show=True),
        Binding("2", "switch_tab('tab-sync')", "Sync", show=True),
        Binding("3", "switch_tab('tab-import')", "Import", show=True),
        Binding("4", "switch_tab('tab-csv')", "CSV", show=True),
        Binding("5", "switch_tab('tab-auth')", "Auth", show=True),
        Binding("r", "refresh_all", "Refresh", show=True),
        Binding("d", "toggle_dark", "Dark Mode", show=False),
    ]

    selected_spotify_id: reactive[str | None] = reactive(None)
    is_busy: reactive[bool] = reactive(False)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-dashboard", id="main-tabs"):
            yield DashboardTab()
            yield SyncStudioTab()
            yield SpotifyImporterTab()
            yield CSVImporterTab()
            yield AuthSettingsTab()
        yield Footer()

    def on_mount(self) -> None:
        ensure_data_dir()
        table = self.query_one("#table-playlists", DataTable)
        table.cursor_type = "cell"
        table.add_columns("#", "Playlist Name", "Spotify ID", "YouTube Music ID")
        self.refresh_all()

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def action_refresh_all(self) -> None:
        self.refresh_all()
        self.notify("Dashboard refreshed", title="spotiyt", severity="information")

    def refresh_all(self) -> None:
        self.refresh_dashboard()
        self.refresh_auth_status()

    def refresh_dashboard(self) -> None:
        data = load_registry()
        table = self.query_one("#table-playlists", DataTable)
        table.clear()

        select_options = []
        for idx, (sid, info) in enumerate(data.items(), 1):
            name = info.get("name", "Untitled")
            ytid = info.get("ytmusic_id", "")
            table.add_row(str(idx), name, sid, ytid, key=sid)
            select_options.append((f"{name} ({sid[:10]}...)", sid))

        sync_select = self.query_one("#sync-select-playlist", Select)
        sync_select.set_options(select_options)

    def refresh_auth_status(self) -> None:
        lbl_cookies = self.query_one("#lbl-ytm-cookies-status", Label)
        lbl_auth = self.query_one("#lbl-ytm-auth-status", Label)

        if AUTH_JSON.exists():
            lbl_auth.update(f"✔ auth.json: [green]Found ({AUTH_JSON.name})[/green]")
        else:
            lbl_auth.update("✖ auth.json: [red]Missing - Click generate below[/red]")

        if COOKIES_JSON.exists():
            lbl_cookies.update(f"✔ ytm-cookies.json: [green]Found ({COOKIES_JSON.name})[/green]")
        else:
            lbl_cookies.update(f"✖ ytm-cookies.json: [yellow]Missing ({COOKIES_JSON.name})[/yellow]")

        lbl_sp_dc = self.query_one("#lbl-spotify-sp-dc-status", Label)

        if SP_DC_FILE.exists() and SP_DC_FILE.read_text().strip():
            lbl_sp_dc.update("✔ sp_dc: [green]Configured[/green]")
        else:
            lbl_sp_dc.update("ℹ sp_dc: [yellow]Not Set (Public playlists work fine)[/yellow]")

    # ==================== Dashboard Handlers ====================

    @on(DataTable.RowSelected, "#table-playlists")
    def on_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key and event.row_key.value:
            self.selected_spotify_id = str(event.row_key.value)

    @on(DataTable.RowHighlighted, "#table-playlists")
    def on_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key and event.row_key.value:
            self.selected_spotify_id = str(event.row_key.value)

    @on(DataTable.CellSelected, "#table-playlists")
    def on_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.coordinate:
            try:
                table = self.query_one("#table-playlists", DataTable)
                row_key, _ = table.coordinate_to_cell_key(event.coordinate)
                if row_key and row_key.value:
                    self.selected_spotify_id = str(row_key.value)
            except Exception:
                pass

    @on(DataTable.CellHighlighted, "#table-playlists")
    def on_table_cell_highlighted(self, event: DataTable.CellHighlighted) -> None:
        if event.coordinate:
            try:
                table = self.query_one("#table-playlists", DataTable)
                row_key, _ = table.coordinate_to_cell_key(event.coordinate)
                if row_key and row_key.value:
                    self.selected_spotify_id = str(row_key.value)
            except Exception:
                pass

    def _ensure_selected_spotify_id(self) -> str | None:
        if self.selected_spotify_id:
            return self.selected_spotify_id
        table = self.query_one("#table-playlists", DataTable)
        if table.row_count > 0 and table.cursor_row is not None and table.cursor_row >= 0:
            try:
                row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
                if row_key and row_key.value:
                    self.selected_spotify_id = str(row_key.value)
                    return self.selected_spotify_id
            except Exception:
                pass
        return None

    @on(Switch.Changed, "#dash-switch-preserve")
    def on_dash_preserve_changed(self, event: Switch.Changed) -> None:
        sync_switch = self.query_one("#sync-switch-preserve", Switch)
        if sync_switch.value != event.value:
            sync_switch.value = event.value

    @on(Switch.Changed, "#sync-switch-preserve")
    def on_sync_preserve_changed(self, event: Switch.Changed) -> None:
        dash_switch = self.query_one("#dash-switch-preserve", Switch)
        if dash_switch.value != event.value:
            dash_switch.value = event.value

    @on(Switch.Changed, "#dash-switch-personalized")
    def on_dash_personalized_changed(self, event: Switch.Changed) -> None:
        sync_switch = self.query_one("#sync-switch-personalized", Switch)
        if sync_switch.value != event.value:
            sync_switch.value = event.value
        auth_select = self.query_one("#import-select-auth", Select)
        target_auth = "personalized" if event.value else "standard"
        if auth_select.value != target_auth:
            auth_select.value = target_auth

    @on(Switch.Changed, "#sync-switch-personalized")
    def on_sync_personalized_changed(self, event: Switch.Changed) -> None:
        dash_switch = self.query_one("#dash-switch-personalized", Switch)
        if dash_switch.value != event.value:
            dash_switch.value = event.value
        auth_select = self.query_one("#import-select-auth", Select)
        target_auth = "personalized" if event.value else "standard"
        if auth_select.value != target_auth:
            auth_select.value = target_auth

    @on(Select.Changed, "#import-select-auth")
    def on_import_auth_changed(self, event: Select.Changed) -> None:
        is_pers = event.value == "personalized"
        dash_switch = self.query_one("#dash-switch-personalized", Switch)
        sync_switch = self.query_one("#sync-switch-personalized", Switch)
        if dash_switch.value != is_pers:
            dash_switch.value = is_pers
        if sync_switch.value != is_pers:
            sync_switch.value = is_pers

    @on(Button.Pressed, "#btn-dash-sync")
    def on_dash_sync_pressed(self) -> None:
        sid = self._ensure_selected_spotify_id()
        if not sid:
            self.notify("Please select a playlist from the table first.", title="Warning", severity="warning")
            return
        data = load_registry()
        info = data.get(sid)
        if not info:
            return
        preserve = self.query_one("#dash-switch-preserve", Switch).value
        personalized = self.query_one("#dash-switch-personalized", Switch).value
        self.trigger_sync(
            sid,
            info["ytmusic_id"],
            preserve=preserve,
            personalized=personalized,
            dry_run=False,
            show_live_modal=True,
        )

    @on(Button.Pressed, "#btn-dash-dry")
    def on_dash_dry_pressed(self) -> None:
        sid = self._ensure_selected_spotify_id()
        if not sid:
            self.notify("Please select a playlist from the table first.", title="Warning", severity="warning")
            return
        data = load_registry()
        info = data.get(sid)
        if not info:
            return
        preserve = self.query_one("#dash-switch-preserve", Switch).value
        personalized = self.query_one("#dash-switch-personalized", Switch).value
        self.trigger_sync(
            sid,
            info["ytmusic_id"],
            preserve=preserve,
            personalized=personalized,
            dry_run=True,
            show_modal=True,
            show_live_modal=True,
        )

    @on(Button.Pressed, "#btn-dash-sync-all")
    def on_dash_sync_all_pressed(self) -> None:
        data = load_registry()
        if not data:
            self.notify("No playlists registered to sync.", title="Warning", severity="warning")
            return
        if self.is_busy:
            self.notify("Another task is currently running. Please wait.", title="Busy", severity="warning")
            return
        preserve = self.query_one("#dash-switch-preserve", Switch).value
        personalized = self.query_one("#dash-switch-personalized", Switch).value

        def handle_confirm(confirmed: bool) -> None:
            if confirmed:
                live_modal = LiveSyncModal(
                    title=f"⚡ Batch Syncing {len(data)} Playlists",
                    subtitle="Starting batch synchronization...",
                )
                self.push_screen(live_modal)
                self.worker_sync_all(
                    preserve=preserve,
                    personalized=personalized,
                    dry_run=False,
                    live_modal=live_modal,
                )

        self.push_screen(
            ConfirmModal(
                title="Sync All Playlists",
                message=f"Are you sure you want to synchronize all {len(data)} registered playlists?",
                confirm_label="Sync All",
            ),
            handle_confirm,
        )

    @on(Button.Pressed, "#btn-dash-dry-all")
    def on_dash_dry_all_pressed(self) -> None:
        data = load_registry()
        if not data:
            self.notify("No playlists registered to preview.", title="Warning", severity="warning")
            return
        if self.is_busy:
            self.notify("Another task is currently running. Please wait.", title="Busy", severity="warning")
            return
        preserve = self.query_one("#dash-switch-preserve", Switch).value
        personalized = self.query_one("#dash-switch-personalized", Switch).value

        live_modal = LiveSyncModal(
            title=f"⚡ Batch Previewing {len(data)} Playlists",
            subtitle="Starting batch dry run...",
        )
        self.push_screen(live_modal)
        self.worker_sync_all(
            preserve=preserve,
            personalized=personalized,
            dry_run=True,
            live_modal=live_modal,
        )

    @on(Button.Pressed, "#btn-dash-add")
    def on_dash_add_pressed(self) -> None:
        def handle_save(result: dict[str, str] | None) -> None:
            if result:
                register_playlist(result["spotify_id"], result["ytmusic_id"], result["name"])
                self.refresh_dashboard()
                self.notify(f"Added '{result['name']}' to registry!", title="Success", severity="information")

        self.push_screen(EditPlaylistModal(title="Add New Playlist Mapping"), handle_save)

    @on(Button.Pressed, "#btn-dash-edit")
    def on_dash_edit_pressed(self) -> None:
        sid = self._ensure_selected_spotify_id()
        if not sid:
            self.notify("Please select a playlist to edit.", title="Warning", severity="warning")
            return
        data = load_registry()
        info = data.get(sid, {})

        def handle_save(result: dict[str, str] | None) -> None:
            if result:
                if result["spotify_id"] != sid and sid in data:
                    data.pop(sid)
                data[result["spotify_id"]] = {
                    "name": result["name"],
                    "ytmusic_id": result["ytmusic_id"],
                }
                save_registry(data)
                self.refresh_dashboard()
                self.notify(f"Updated '{result['name']}'!", title="Success", severity="information")

        self.push_screen(
            EditPlaylistModal(
                title=f"Edit: {info.get('name', 'Playlist')}",
                name=info.get("name", ""),
                spotify_id=sid,
                ytmusic_id=info.get("ytmusic_id", ""),
            ),
            handle_save,
        )

    @on(Button.Pressed, "#btn-dash-del")
    def on_dash_del_pressed(self) -> None:
        sid = self._ensure_selected_spotify_id()
        if not sid:
            self.notify("Please select a playlist to delete.", title="Warning", severity="warning")
            return
        data = load_registry()
        info = data.get(sid, {})
        pname = info.get("name", sid)

        def handle_confirm(confirmed: bool) -> None:
            if confirmed and sid:
                data.pop(sid, None)
                save_registry(data)
                self.selected_spotify_id = None
                self.refresh_dashboard()
                self.notify(f"Removed '{pname}' from registry.", title="Deleted", severity="warning")

        self.push_screen(
            ConfirmModal(
                title=f"Delete '{pname}'?",
                message="This will remove the mapping from playlists.json (will not delete playlists from Spotify or YouTube).",
                confirm_label="Delete Mapping",
                is_danger=True,
            ),
            handle_confirm,
        )

    @on(Button.Pressed, "#btn-dash-del-all")
    def on_dash_del_all_pressed(self) -> None:
        data = load_registry()
        if not data:
            return

        def handle_confirm(confirmed: bool) -> None:
            if confirmed:
                save_registry({})
                self.selected_spotify_id = None
                self.refresh_dashboard()
                self.notify("All playlist mappings deleted.", title="Deleted", severity="warning")

        self.push_screen(
            ConfirmModal(
                title="Delete ALL Playlist Mappings?",
                message=f"Are you sure you want to remove all {len(data)} playlists from playlists.json?",
                confirm_label="Delete ALL",
                is_danger=True,
            ),
            handle_confirm,
        )

    # ==================== Sync Studio Handlers ====================

    @on(Select.Changed, "#sync-select-playlist")
    def on_sync_select_changed(self, event: Select.Changed) -> None:
        if event.value and event.value != Select.BLANK:
            data = load_registry()
            sid = str(event.value)
            if sid in data:
                self.selected_spotify_id = sid
                self.query_one("#sync-input-spotify-id", Input).value = sid
                self.query_one("#sync-input-ytmusic-id", Input).value = data[sid].get("ytmusic_id", "")

    @on(Button.Pressed, "#btn-sync-start")
    def on_sync_start_pressed(self) -> None:
        raw_sid = self.query_one("#sync-input-spotify-id", Input).value.strip()
        ytid = self.query_one("#sync-input-ytmusic-id", Input).value.strip()
        sid = extract_spotify_id(raw_sid)
        if not sid:
            self.notify("Please enter a valid Spotify Playlist ID or URL.", title="Invalid Input", severity="error")
            return
        if not ytid:
            self.notify("Please enter a YouTube Music Playlist ID.", title="Invalid Input", severity="error")
            return

        preserve = self.query_one("#sync-switch-preserve", Switch).value
        personalized = self.query_one("#sync-switch-personalized", Switch).value
        dry_run = self.query_one("#sync-switch-dry", Switch).value

        self.trigger_sync(sid, ytid, preserve, personalized, dry_run, show_live_modal=False)

    @on(Button.Pressed, "#btn-sync-preview")
    def on_sync_preview_pressed(self) -> None:
        raw_sid = self.query_one("#sync-input-spotify-id", Input).value.strip()
        ytid = self.query_one("#sync-input-ytmusic-id", Input).value.strip()
        sid = extract_spotify_id(raw_sid)
        if not sid or not ytid:
            self.notify("Please specify both Spotify ID and YouTube Music ID.", title="Warning", severity="warning")
            return

        preserve = self.query_one("#sync-switch-preserve", Switch).value
        personalized = self.query_one("#sync-switch-personalized", Switch).value

        self.trigger_sync(sid, ytid, preserve, personalized, dry_run=True, show_modal=True, show_live_modal=False)

    @on(Button.Pressed, "#btn-sync-clear")
    def on_sync_clear_pressed(self) -> None:
        self.query_one("#sync-log", RichLog).clear()
        self.query_one("#sync-progress", ProgressBar).update(progress=0, total=100)

    @on(Button.Pressed, "#btn-sync-reset")
    def on_sync_reset_pressed(self) -> None:
        self.query_one("#sync-input-spotify-id", Input).value = ""
        self.query_one("#sync-input-ytmusic-id", Input).value = ""
        sync_select = self.query_one("#sync-select-playlist", Select)
        sync_select.clear()
        self.notify("Sync Studio inputs cleared.", title="Reset", severity="information")

    def trigger_sync(
        self,
        sid: str,
        ytid: str,
        preserve: bool,
        personalized: bool,
        dry_run: bool,
        show_modal: bool = False,
        show_live_modal: bool = True,
    ) -> None:
        if self.is_busy:
            self.notify("Another task is currently running. Please wait.", title="Busy", severity="warning")
            return

        live_modal: LiveSyncModal | None = None
        if show_live_modal:
            data = load_registry()
            pl_name = data.get(sid, {}).get("name", sid)
            title = f"Previewing: {pl_name}" if dry_run else f"Syncing: {pl_name}"
            live_modal = LiveSyncModal(
                title=f"🔄 {title}",
                subtitle="Initializing sync engine...",
            )
            self.push_screen(live_modal)

        self.worker_sync(
            sid,
            ytid,
            preserve,
            personalized,
            dry_run,
            show_modal=show_modal,
            live_modal=live_modal,
        )

    # ==================== Spotify Importer Handlers ====================

    @on(Button.Pressed, "#btn-import-start")
    def on_import_start_pressed(self) -> None:
        if self.is_busy:
            self.notify("Another task is running. Please wait.", title="Busy", severity="warning")
            return

        raw_url = self.query_one("#import-input-url", Input).value.strip()
        sid = extract_spotify_id(raw_url)
        if not sid:
            self.notify("Invalid Spotify Playlist URL or ID.", title="Error", severity="error")
            return

        auth_mode = self.query_one("#import-select-auth", Select).value
        personalized = auth_mode == "personalized"
        out_dir = self.query_one("#import-input-output", Input).value.strip() or str(EXPORTS_DIR)
        dry_run = self.query_one("#import-switch-dry", Switch).value

        self.worker_import(sid, personalized, out_dir, dry_run)

    @on(Button.Pressed, "#btn-import-clear")
    def on_import_clear_pressed(self) -> None:
        self.query_one("#import-log", RichLog).clear()
        self.query_one("#import-progress", ProgressBar).update(progress=0, total=100)

    # ==================== CSV Importer Handlers ====================

    @on(Button.Pressed, "#btn-csv-start")
    def on_csv_start_pressed(self) -> None:
        if self.is_busy:
            self.notify("Another task is running. Please wait.", title="Busy", severity="warning")
            return

        csv_path = self.query_one("#csv-input-path", Input).value.strip()
        if not csv_path or not Path(csv_path).exists():
            self.notify(f"CSV file not found: {csv_path}", title="File Not Found", severity="error")
            return

        pname = self.query_one("#csv-input-name", Input).value.strip()
        if not pname:
            pname = Path(csv_path).stem.replace("_", " ").title()
        pdesc = self.query_one("#csv-input-desc", Input).value.strip() or "Imported from CSV"

        self.worker_csv_import(csv_path, pname, pdesc)

    @on(Button.Pressed, "#btn-csv-clear")
    def on_csv_clear_pressed(self) -> None:
        self.query_one("#csv-log", RichLog).clear()
        self.query_one("#csv-progress", ProgressBar).update(progress=0, total=100)

    # ==================== Auth & Settings Handlers ====================

    @on(Button.Pressed, "#btn-auth-generate")
    def on_auth_generate_pressed(self) -> None:
        if self.is_busy:
            self.notify("Another task is running. Please wait.", title="Busy", severity="warning")
            return
        self.worker_auth_generate()

    @on(Button.Pressed, "#btn-save-sp-dc")
    def on_save_sp_dc_pressed(self) -> None:
        sp_dc_input = self.query_one("#input-sp-dc-cookie", Input)
        val = sp_dc_input.value.strip()
        if not val:
            self.notify("Please enter a non-empty sp_dc cookie.", title="Warning", severity="warning")
            return

        ensure_data_dir()
        SP_DC_FILE.write_text(val + "\n")
        sp_dc_input.value = ""
        self.refresh_auth_status()
        self.notify("Spotify 'sp_dc' cookie saved successfully!", title="Success", severity="information")

    # ==================== Background Workers ====================

    def _make_logger(self, rich_log: RichLog, live_modal: LiveSyncModal | None = None):
        def log_cb(level: str, msg: str):
            prefix = {
                "success": "[bold green]✔[/bold green] ",
                "error": "[bold red]✖[/bold red] ",
                "warning": "[bold yellow]⚠[/bold yellow] ",
                "info": "[bold cyan]ℹ[/bold cyan] ",
                "dim": "  [dim]•[/dim] ",
            }.get(level, "")
            formatted = f"{prefix}{msg}"
            self.call_from_thread(rich_log.write, formatted)
            if live_modal:
                self.call_from_thread(live_modal.write_log, formatted)

        return log_cb

    def _make_progress(self, progress_bar: ProgressBar, live_modal: LiveSyncModal | None = None):
        def progress_cb(current: int, total: int, description: str):
            def update_ui():
                if total > 0:
                    progress_bar.update(total=total, progress=current)
                if live_modal:
                    live_modal.update_progress(current, total, description)

            self.call_from_thread(update_ui)

        return progress_cb

    @work(thread=True, exclusive=True)
    def worker_sync(
        self,
        sid: str,
        ytid: str,
        preserve: bool,
        personalized: bool,
        dry_run: bool,
        show_modal: bool = False,
        live_modal: LiveSyncModal | None = None,
    ) -> None:
        self.is_busy = True
        rich_log = self.query_one("#sync-log", RichLog)
        progress_bar = self.query_one("#sync-progress", ProgressBar)
        self.call_from_thread(progress_bar.update, progress=0, total=100)

        log_cb = self._make_logger(rich_log, live_modal=live_modal)
        progress_cb = self._make_progress(progress_bar, live_modal=live_modal)

        try:
            log_cb("info", f"Initiating sync for Spotify playlist [bold]{sid}[/bold] ➔ [bold]{ytid}[/bold]...")
            summary = sync(
                sid,
                ytid,
                preserve=preserve,
                personalized=personalized,
                dry_run=dry_run,
                log_cb=log_cb,
                progress_cb=progress_cb,
            )
            self.call_from_thread(progress_bar.update, progress=100, total=100)

            if dry_run and show_modal:
                if live_modal:
                    self.call_from_thread(live_modal.dismiss)
                self.call_from_thread(self.push_screen, DryRunModal(summary))
            elif dry_run:
                if live_modal:
                    self.call_from_thread(live_modal.set_complete, "Dry run preview completed.", is_success=True)
                self.call_from_thread(
                    self.notify, "Dry run preview completed.", title="Dry Run", severity="information"
                )
            else:
                added = summary.get("added", 0)
                removed = summary.get("removed", 0)
                if live_modal:
                    self.call_from_thread(
                        live_modal.set_complete,
                        f"Sync completed! Added: {added}, Removed: {removed}",
                        is_success=True,
                    )
                self.call_from_thread(
                    self.notify,
                    f"Sync completed! Added: {added}, Removed: {removed}",
                    title="Sync Finished",
                    severity="information",
                )

        except Exception as e:
            log_cb("error", f"Sync failed: {e}")
            if live_modal:
                self.call_from_thread(live_modal.set_complete, f"Failed: {e}", is_success=False)
            self.call_from_thread(self.notify, f"Sync failed: {e}", title="Error", severity="error")
        finally:
            self.is_busy = False

    @work(thread=True, exclusive=True)
    def worker_sync_all(
        self,
        preserve: bool,
        personalized: bool,
        dry_run: bool,
        live_modal: LiveSyncModal | None = None,
    ) -> None:
        self.is_busy = True
        rich_log = self.query_one("#sync-log", RichLog)
        progress_bar = self.query_one("#sync-progress", ProgressBar)
        self.call_from_thread(rich_log.clear)

        log_cb = self._make_logger(rich_log, live_modal=live_modal)
        progress_cb = self._make_progress(progress_bar, live_modal=live_modal)

        data = load_registry()
        total_pls = len(data)
        success_count = 0

        try:
            log_cb("info", f"Starting batch synchronization of {total_pls} playlist(s)...")
            for idx, (sid, info) in enumerate(data.items(), 1):
                pname = info.get("name", "Untitled")
                ytid = info.get("ytmusic_id", "")
                if live_modal:
                    self.call_from_thread(
                        live_modal.update_progress,
                        int(((idx - 1) / total_pls) * 100),
                        100,
                        f"[{idx}/{total_pls}] Syncing: {pname}",
                    )
                log_cb("info", f"\n[{idx}/{total_pls}] Processing: [bold cyan]{pname}[/bold cyan] ({sid})")

                try:
                    sync(
                        sid,
                        ytid,
                        preserve=preserve,
                        personalized=personalized,
                        dry_run=dry_run,
                        log_cb=log_cb,
                        progress_cb=progress_cb,
                    )
                    success_count += 1
                except Exception as e:
                    log_cb("error", f"Failed syncing '{pname}': {e}")

            if live_modal:
                self.call_from_thread(
                    live_modal.set_complete,
                    f"Batch sync finished ({success_count}/{total_pls} successful)",
                    is_success=True,
                )
            log_cb("success", f"\nBatch sync completed for {success_count}/{total_pls} playlists.")
            self.call_from_thread(
                self.notify,
                f"Batch sync finished ({success_count}/{total_pls} successful)",
                title="Batch Sync",
                severity="information",
            )
        except Exception as e:
            log_cb("error", f"Batch sync error: {e}")
            if live_modal:
                self.call_from_thread(live_modal.set_complete, f"Batch sync error: {e}", is_success=False)
        finally:
            self.is_busy = False

    @work(thread=True, exclusive=True)
    def worker_import(self, sid: str, personalized: bool, output_dir: str, dry_run: bool) -> None:
        self.is_busy = True
        rich_log = self.query_one("#import-log", RichLog)
        progress_bar = self.query_one("#import-progress", ProgressBar)
        self.call_from_thread(progress_bar.update, progress=0, total=100)

        log_cb = self._make_logger(rich_log)
        progress_cb = self._make_progress(progress_bar)

        try:
            log_cb("info", f"Authenticating and fetching Spotify playlist: [bold cyan]{sid}[/bold cyan]...")
            token = get_token(personalized)
            name, items = fetch_playlist(token, sid, log_cb=log_cb, progress_cb=progress_cb)

            sanitized = sanitize_filename(name) or sid
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            output_file = str(out_dir / f"{sanitized}.csv")

            save_csv(name, items, output_file, log_cb=log_cb)

            if dry_run:
                log_cb("info", "Dry Run Mode: Exported CSV. Skipped YouTube Music playlist creation.")
                self.call_from_thread(
                    self.notify, f"Exported {len(items)} tracks to CSV.", title="Import Dry Run", severity="information"
                )
                return

            log_cb("info", "Importing CSV to YouTube Music...")
            yt_id = import_to_ytmusic(
                output_file,
                f"{name} (Spotify)",
                "Imported from Spotify",
                log_cb=log_cb,
                progress_cb=progress_cb,
            )

            if yt_id:
                register_playlist(sid, yt_id, name)
                self.call_from_thread(self.refresh_dashboard)
                log_cb("success", f"Successfully registered playlist in registry: '{name}'")
                self.call_from_thread(
                    self.notify,
                    f"Playlist '{name}' imported and registered!",
                    title="Import Complete",
                    severity="information",
                )

        except Exception as e:
            log_cb("error", f"Import failed for {sid}: {e}")
            self.call_from_thread(self.notify, f"Import failed: {e}", title="Import Error", severity="error")
        finally:
            self.is_busy = False

    @work(thread=True, exclusive=True)
    def worker_csv_import(self, csv_path: str, playlist_name: str, description: str) -> None:
        self.is_busy = True
        rich_log = self.query_one("#csv-log", RichLog)
        progress_bar = self.query_one("#csv-progress", ProgressBar)
        self.call_from_thread(progress_bar.update, progress=0, total=100)

        log_cb = self._make_logger(rich_log)
        progress_cb = self._make_progress(progress_bar)

        try:
            log_cb("info", f"Starting CSV import from [cyan]{csv_path}[/cyan]...")
            yt_id = import_to_ytmusic(
                csv_path,
                playlist_name,
                description=description,
                log_cb=log_cb,
                progress_cb=progress_cb,
            )
            if yt_id:
                self.call_from_thread(
                    self.notify,
                    f"Playlist '{playlist_name}' created on YouTube Music!",
                    title="CSV Imported",
                    severity="information",
                )
        except Exception as e:
            log_cb("error", f"CSV import failed: {e}")
            self.call_from_thread(self.notify, f"CSV import failed: {e}", title="CSV Error", severity="error")
        finally:
            self.is_busy = False

    @work(thread=True, exclusive=True)
    def worker_auth_generate(self) -> None:
        self.is_busy = True
        try:
            success = refresh_from_cookies_json()
            self.call_from_thread(self.refresh_auth_status)
            if success:
                self.call_from_thread(
                    self.notify,
                    "Generated auth.json from cookies successfully!",
                    title="Auth Success",
                    severity="information",
                )
            else:
                self.call_from_thread(
                    self.notify,
                    "Failed to generate auth.json. Check ytm-cookies.json.",
                    title="Auth Failed",
                    severity="error",
                )
        except Exception as e:
            self.call_from_thread(self.notify, f"Auth generation error: {e}", title="Error", severity="error")
        finally:
            self.is_busy = False
