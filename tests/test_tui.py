"""Comprehensive unit and pilot tests for SpotiYT Textual TUI."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    RichLog,
    Select,
    Switch,
    TabbedContent,
)

from spotiyt.tui.app import SpotiYTApp
from spotiyt.tui.screens.modals import ConfirmModal, DryRunModal, EditPlaylistModal


class TestSpotiYTTUI(unittest.IsolatedAsyncioTestCase):
    """Test suite for Textual UI components and application workflows."""

    async def test_app_mount_and_tabs(self):
        app = SpotiYTApp()
        async with app.run_test(size=(120, 40)) as pilot:
            tabs = app.query_one("#main-tabs", TabbedContent)
            self.assertEqual(tabs.active, "tab-dashboard")

            # Switch tabs using keys
            await pilot.press("2")
            self.assertEqual(tabs.active, "tab-sync")

            await pilot.press("3")
            self.assertEqual(tabs.active, "tab-import")

            await pilot.press("4")
            self.assertEqual(tabs.active, "tab-csv")

            await pilot.press("5")
            self.assertEqual(tabs.active, "tab-auth")

            await pilot.press("1")
            self.assertEqual(tabs.active, "tab-dashboard")

    async def test_dashboard_renders_registry(self):
        sample_registry = {
            "37i9dQZF1E8MCNiiTgwMk8": {
                "name": "Discover Weekly",
                "ytmusic_id": "PL_sample_ytm_1",
            },
            "4a9dQZF1E8MCNiiTgwMk9": {
                "name": "Release Radar",
                "ytmusic_id": "PL_sample_ytm_2",
            },
        }

        with patch("spotiyt.tui.app.load_registry", return_value=sample_registry):
            app = SpotiYTApp()
            async with app.run_test(size=(120, 40)) as pilot:
                app.refresh_dashboard()
                await pilot.pause()

                table = app.query_one("#table-playlists", DataTable)
                self.assertEqual(table.row_count, 2)

                stat_count = app.query_one("#stat-playlists-count", Label)
                self.assertEqual(str(stat_count.render()), "2")

                # Verify dropdown options populated
                sync_select = app.query_one("#sync-select-playlist", Select)
                user_options = [opt for opt in sync_select._options if opt[1] not in (Select.BLANK, Select.NULL)]
                self.assertEqual(len(user_options), 2)

    async def test_sync_studio_inputs_and_switches(self):
        sample_registry = {
            "spotify_test_id": {
                "name": "Test Hits",
                "ytmusic_id": "ytm_test_id",
            }
        }

        with patch("spotiyt.tui.app.load_registry", return_value=sample_registry):
            app = SpotiYTApp()
            async with app.run_test(size=(120, 40)) as pilot:
                app.refresh_dashboard()
                tabs = app.query_one("#main-tabs", TabbedContent)
                tabs.active = "tab-sync"
                await pilot.pause()

                # Change select
                sync_select = app.query_one("#sync-select-playlist", Select)
                sync_select.value = "spotify_test_id"
                await pilot.pause()

                sid_input = app.query_one("#sync-input-spotify-id", Input)
                ytid_input = app.query_one("#sync-input-ytmusic-id", Input)
                self.assertEqual(sid_input.value, "spotify_test_id")
                self.assertEqual(ytid_input.value, "ytm_test_id")

                # Test switch toggling
                preserve_switch = app.query_one("#sync-switch-preserve", Switch)
                preserve_switch.value = True
                self.assertTrue(preserve_switch.value)

                # Clear log button
                rich_log = app.query_one("#sync-log", RichLog)
                rich_log.write("Sample message")
                await pilot.pause()
                app.query_one("#btn-sync-clear", Button).press()
                await pilot.pause()
                self.assertEqual(len(rich_log.lines), 0)

    async def test_spotify_importer_tab(self):
        app = SpotiYTApp()
        async with app.run_test(size=(120, 40)) as pilot:
            tabs = app.query_one("#main-tabs", TabbedContent)
            tabs.active = "tab-import"
            await pilot.pause()

            url_input = app.query_one("#import-input-url", Input)
            url_input.value = "https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8"
            await pilot.pause()

            auth_select = app.query_one("#import-select-auth", Select)
            auth_select.value = "personalized"
            await pilot.pause()
            self.assertEqual(auth_select.value, "personalized")

    async def test_csv_importer_tab(self):
        app = SpotiYTApp()
        async with app.run_test(size=(120, 40)) as pilot:
            tabs = app.query_one("#main-tabs", TabbedContent)
            tabs.active = "tab-csv"
            await pilot.pause()

            path_input = app.query_one("#csv-input-path", Input)
            path_input.value = "/path/to/my_favorite_songs.csv"
            name_input = app.query_one("#csv-input-name", Input)
            name_input.value = "Custom Playlist"
            await pilot.pause()

            self.assertEqual(path_input.value, "/path/to/my_favorite_songs.csv")
            self.assertEqual(name_input.value, "Custom Playlist")

    async def test_auth_tab_save_sp_dc(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_sp_dc = Path(tmpdir) / "sp_dc.txt"
            with patch("spotiyt.tui.app.SP_DC_FILE", temp_sp_dc):
                app = SpotiYTApp()
                async with app.run_test(size=(120, 40)) as pilot:
                    tabs = app.query_one("#main-tabs", TabbedContent)
                    tabs.active = "tab-auth"
                    await pilot.pause()

                    sp_input = app.query_one("#input-sp-dc-cookie", Input)
                    sp_input.value = "my_secret_sp_dc_cookie_123"
                    app.query_one("#btn-save-sp-dc", Button).press()
                    await pilot.pause()

                    self.assertTrue(temp_sp_dc.exists())
                    self.assertIn("my_secret_sp_dc_cookie_123", temp_sp_dc.read_text())


class TestModals(unittest.IsolatedAsyncioTestCase):
    """Test suite for TUI Modal dialogs."""

    async def test_confirm_modal_confirm(self):
        app = SpotiYTApp()
        async with app.run_test(size=(120, 40)) as pilot:
            result_container = []

            def callback(res):
                result_container.append(res)

            modal = ConfirmModal(title="Test Confirm", message="Please confirm")
            app.push_screen(modal, callback)
            await pilot.pause()

            modal.query_one("#btn-confirm", Button).press()
            await pilot.pause()

            self.assertEqual(result_container, [True])

    async def test_confirm_modal_cancel(self):
        app = SpotiYTApp()
        async with app.run_test(size=(120, 40)) as pilot:
            result_container = []

            def callback(res):
                result_container.append(res)

            modal = ConfirmModal(title="Test Cancel", message="Please confirm")
            app.push_screen(modal, callback)
            await pilot.pause()

            modal.query_one("#btn-cancel", Button).press()
            await pilot.pause()

            self.assertEqual(result_container, [False])

    async def test_edit_playlist_modal_validation(self):
        app = SpotiYTApp()
        async with app.run_test(size=(120, 40)) as pilot:
            result_container = []

            def callback(res):
                result_container.append(res)

            modal = EditPlaylistModal()
            app.push_screen(modal, callback)
            await pilot.pause()

            # Fill in valid fields
            modal.query_one("#input-name", Input).value = "Rock Classics"
            modal.query_one(
                "#input-spotify-id", Input
            ).value = "https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8"
            modal.query_one("#input-ytmusic-id", Input).value = "PL_ytm_rock_123"
            modal.query_one("#btn-save", Button).press()
            await pilot.pause()

            self.assertEqual(len(result_container), 1)
            self.assertEqual(result_container[0]["name"], "Rock Classics")
            self.assertEqual(result_container[0]["spotify_id"], "37i9dQZF1E8MCNiiTgwMk8")
            self.assertEqual(result_container[0]["ytmusic_id"], "PL_ytm_rock_123")

    async def test_dry_run_modal_render(self):
        summary = {
            "spotify_name": "My Dry Run Playlist",
            "spotify_tracks_count": 10,
            "matched_count": 8,
            "to_add_count": 2,
            "to_remove_count": 1,
            "to_add_items": [("vid_1", "New Track", "Artist 1")],
            "to_remove_items": [{"title": "Old Track", "artists": "Artist 2"}],
            "not_found_items": [],
        }

        app = SpotiYTApp()
        async with app.run_test(size=(120, 40)) as pilot:
            modal = DryRunModal(summary)
            app.push_screen(modal)
            await pilot.pause()

            table = modal.query_one("#diff-table", DataTable)
            self.assertEqual(table.row_count, 2)

            modal.query_one("#btn-close", Button).press()
            await pilot.pause()


if __name__ == "__main__":
    unittest.main()
