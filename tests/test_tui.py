"""Comprehensive unit and pilot tests for SpotiYT Textual TUI using pytest."""

from pathlib import Path
from unittest.mock import patch

from textual.widgets import (
    Button,
    DataTable,
    Input,
    RichLog,
    Select,
    Switch,
    TabbedContent,
)

from spotiyt.tui.app import SpotiYTApp
from spotiyt.tui.screens.modals import ConfirmModal, DryRunModal, EditPlaylistModal


async def test_app_mount_and_tabs():
    app = SpotiYTApp()
    async with app.run_test(size=(120, 40)) as pilot:
        tabs = app.query_one("#main-tabs", TabbedContent)
        assert tabs.active == "tab-dashboard"

        # Switch tabs using keys
        await pilot.press("2")
        assert tabs.active == "tab-sync"

        await pilot.press("3")
        assert tabs.active == "tab-import"

        await pilot.press("4")
        assert tabs.active == "tab-csv"

        await pilot.press("5")
        assert tabs.active == "tab-auth"

        await pilot.press("1")
        assert tabs.active == "tab-dashboard"


async def test_dashboard_renders_registry():
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
            assert table.row_count == 2

            # Verify dropdown options populated
            sync_select = app.query_one("#sync-select-playlist", Select)
            user_options = [opt for opt in sync_select._options if opt[1] not in (Select.BLANK, Select.NULL)]
            assert len(user_options) == 2


async def test_dashboard_sync_action_switches_tab():
    sample_registry = {
        "37i9dQZF1E8MCNiiTgwMk8": {
            "name": "Discover Weekly",
            "ytmusic_id": "PL_sample_ytm_1",
        }
    }

    with patch("spotiyt.tui.app.load_registry", return_value=sample_registry), patch("spotiyt.tui.app.sync"):
        app = SpotiYTApp()
        async with app.run_test(size=(120, 40)) as pilot:
            app.refresh_dashboard()
            await pilot.pause()

            # Select playlist in table
            table = app.query_one("#table-playlists", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            # Click Sync Selected
            app.query_one("#btn-dash-sync", Button).press()
            await pilot.pause()

            # Verify tab automatically switched to tab-sync
            tabs = app.query_one("#main-tabs", TabbedContent)
            assert tabs.active == "tab-sync"

            # Verify sync inputs populated
            assert app.query_one("#sync-input-spotify-id", Input).value == "37i9dQZF1E8MCNiiTgwMk8"
            assert app.query_one("#sync-input-ytmusic-id", Input).value == "PL_sample_ytm_1"


async def test_dashboard_switches_cross_synchronization():
    app = SpotiYTApp()
    async with app.run_test(size=(120, 40)) as pilot:
        dash_preserve = app.query_one("#dash-switch-preserve", Switch)
        sync_preserve = app.query_one("#sync-switch-preserve", Switch)
        dash_pers = app.query_one("#dash-switch-personalized", Switch)
        sync_pers = app.query_one("#sync-switch-personalized", Switch)
        import_auth = app.query_one("#import-select-auth", Select)

        # Toggle on dashboard -> updates sync studio
        dash_preserve.value = True
        await pilot.pause()
        assert sync_preserve.value is True

        dash_pers.value = True
        await pilot.pause()
        assert sync_pers.value is True
        assert import_auth.value == "personalized"

        # Toggle in import tab -> updates dashboard & sync
        import_auth.value = "standard"
        await pilot.pause()
        assert dash_pers.value is False
        assert sync_pers.value is False


async def test_sync_studio_inputs_and_switches():
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
            assert sid_input.value == "spotify_test_id"
            assert ytid_input.value == "ytm_test_id"

            # Test switch toggling
            preserve_switch = app.query_one("#sync-switch-preserve", Switch)
            preserve_switch.value = True
            assert preserve_switch.value is True

            # Clear log button
            rich_log = app.query_one("#sync-log", RichLog)
            rich_log.write("Sample message")
            await pilot.pause()
            app.query_one("#btn-sync-clear", Button).press()
            await pilot.pause()
            assert len(rich_log.lines) == 0


async def test_spotify_importer_tab():
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
        assert auth_select.value == "personalized"


async def test_csv_importer_tab():
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

        assert path_input.value == "/path/to/my_favorite_songs.csv"
        assert name_input.value == "Custom Playlist"


async def test_auth_tab_save_sp_dc(tmp_path: Path):
    temp_sp_dc = tmp_path / "sp_dc.txt"
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

            assert temp_sp_dc.exists()
            assert "my_secret_sp_dc_cookie_123" in temp_sp_dc.read_text()


async def test_confirm_modal_confirm():
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

        assert result_container == [True]


async def test_confirm_modal_cancel():
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

        assert result_container == [False]


async def test_edit_playlist_modal_validation():
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
        modal.query_one("#input-spotify-id", Input).value = "https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8"
        modal.query_one("#input-ytmusic-id", Input).value = "PL_ytm_rock_123"
        modal.query_one("#btn-save", Button).press()
        await pilot.pause()

        assert len(result_container) == 1
        assert result_container[0]["name"] == "Rock Classics"
        assert result_container[0]["spotify_id"] == "37i9dQZF1E8MCNiiTgwMk8"
        assert result_container[0]["ytmusic_id"] == "PL_ytm_rock_123"


async def test_dry_run_modal_render():
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
        assert table.row_count == 2

        modal.query_one("#btn-close", Button).press()
        await pilot.pause()


async def test_small_screen_termux_compatibility():
    """Test that SpotiYTApp runs smoothly on compact Termux-sized screens (e.g. 50x22)."""
    sample_registry = {
        "37i9dQZF1E8MCNiiTgwMk8": {
            "name": "Discover Weekly",
            "ytmusic_id": "PL_sample_ytm_1",
        }
    }

    with patch("spotiyt.tui.app.load_registry", return_value=sample_registry):
        app = SpotiYTApp()
        async with app.run_test(size=(50, 22)) as pilot:
            # Mounts without crash on mobile dimensions
            app.refresh_dashboard()
            await pilot.pause()

            # Dashboard rendered
            table = app.query_one("#table-playlists", DataTable)
            assert table.row_count == 1

            # Switch through tabs smoothly on small screen
            await pilot.press("2")
            assert app.query_one("#main-tabs", TabbedContent).active == "tab-sync"

            await pilot.press("3")
            assert app.query_one("#main-tabs", TabbedContent).active == "tab-import"

            await pilot.press("4")
            assert app.query_one("#main-tabs", TabbedContent).active == "tab-csv"

            await pilot.press("5")
            assert app.query_one("#main-tabs", TabbedContent).active == "tab-auth"
