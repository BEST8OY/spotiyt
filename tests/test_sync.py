from unittest.mock import patch

from spotiyt.sync import find_unmatched, sync


def test_find_unmatched():
    spotify_tracks = [
        {"name": "Song A", "artists": "Artist A"},
        {"name": "Song B", "artists": "Artist B"},
        {"name": "Song C", "artists": "Artist C"},
    ]
    yt_tracks = [
        {"videoId": "vid_a", "title": "Song A", "artists": "Artist A"},
        {"videoId": "vid_old", "title": "Song Old", "artists": "Artist Old"},
    ]

    unmatched_spotify, matched_ids, unmatched_yt = find_unmatched(spotify_tracks, yt_tracks)

    assert matched_ids == ["vid_a"]
    assert len(unmatched_spotify) == 2
    assert [t["name"] for t in unmatched_spotify] == ["Song B", "Song C"]
    assert len(unmatched_yt) == 1
    assert unmatched_yt[0]["videoId"] == "vid_old"


@patch("spotiyt.sync.get_ytmusic_client")
@patch("spotiyt.sync.get_token")
@patch("spotiyt.sync.fetch_playlist")
@patch("spotiyt.sync.get_yt_playlist")
@patch("spotiyt.sync.search_tracks")
@patch("spotiyt.sync.add_in_batches")
@patch("spotiyt.sync.remove_in_batches")
@patch("spotiyt.sync.console")
def test_sync_prints_added_tracks(
    mock_console,
    mock_remove,
    mock_add,
    mock_search,
    mock_get_yt_pl,
    mock_fetch_pl,
    mock_get_token,
    mock_get_client,
):
    mock_get_token.return_value = "fake_token"
    mock_fetch_pl.return_value = (
        "Test Spotify PL",
        [
            {"itemV2": {"data": {"name": "New Song 1", "artists": {"items": [{"profile": {"name": "Artist 1"}}]}}}},
            {"itemV2": {"data": {"name": "Existing Song", "artists": {"items": [{"profile": {"name": "Artist 2"}}]}}}},
        ],
    )
    mock_get_yt_pl.return_value = (
        "Test YT PL",
        [{"videoId": "vid_exist", "title": "Existing Song", "artists": "Artist 2"}],
    )
    mock_search.return_value = ([("vid_new1", "New Song 1", "Artist 1")], [])
    mock_add.return_value = (1, 0)

    sync("spotify_123", "yt_123", preserve=False, dry_run=False)

    mock_search.assert_called_once()
    mock_add.assert_called_once_with(mock_get_client.return_value, "yt_123", ["vid_new1"])

    printed_texts = [call.args[0] for call in mock_console.print.call_args_list if call.args]
    added_track_printed = any(
        "[green]New Song 1[/green]" in text and "Artist 1" in text for text in printed_texts if isinstance(text, str)
    )
    assert added_track_printed, "Expected added track to be printed to console"


@patch("spotiyt.sync.get_ytmusic_client")
@patch("spotiyt.sync.get_token")
@patch("spotiyt.sync.fetch_playlist")
@patch("spotiyt.sync.get_yt_playlist")
@patch("spotiyt.sync.search_tracks")
@patch("spotiyt.sync.add_in_batches")
@patch("spotiyt.sync.remove_in_batches")
@patch("spotiyt.sync.console")
def test_sync_dry_run_prints_added_and_removed(
    mock_console,
    mock_remove,
    mock_add,
    mock_search,
    mock_get_yt_pl,
    mock_fetch_pl,
    mock_get_token,
    mock_get_client,
):
    mock_get_token.return_value = "fake_token"
    mock_fetch_pl.return_value = (
        "Test Spotify PL",
        [
            {"itemV2": {"data": {"name": "New Song 1", "artists": {"items": [{"profile": {"name": "Artist 1"}}]}}}},
        ],
    )
    mock_get_yt_pl.return_value = (
        "Test YT PL",
        [{"videoId": "vid_old", "title": "Old Song", "artists": "Artist Old"}],
    )
    mock_search.return_value = ([("vid_new1", "New Song 1", "Artist 1")], [])

    sync("spotify_123", "yt_123", preserve=False, dry_run=True)

    mock_add.assert_not_called()
    mock_remove.assert_not_called()

    printed_texts = [call.args[0] for call in mock_console.print.call_args_list if call.args]
    added_track_printed = any(
        "[green]New Song 1[/green]" in text and "Artist 1" in text for text in printed_texts if isinstance(text, str)
    )
    removed_track_printed = any(
        "[red]Old Song[/red]" in text and "Artist Old" in text for text in printed_texts if isinstance(text, str)
    )
    assert added_track_printed, "Expected added track in dry run preview"
    assert removed_track_printed, "Expected removed track in dry run preview"


@patch("spotiyt.sync.get_ytmusic_client")
@patch("spotiyt.sync.get_token")
@patch("spotiyt.sync.fetch_playlist")
@patch("spotiyt.sync.get_yt_playlist")
@patch("spotiyt.sync.search_tracks")
@patch("spotiyt.sync.add_in_batches")
@patch("spotiyt.sync.remove_in_batches")
@patch("spotiyt.sync.console")
def test_sync_deduplicates_added_tracks(
    mock_console,
    mock_remove,
    mock_add,
    mock_search,
    mock_get_yt_pl,
    mock_fetch_pl,
    mock_get_token,
    mock_get_client,
):
    mock_get_token.return_value = "fake_token"
    mock_fetch_pl.return_value = (
        "Test Spotify PL",
        [
            {"itemV2": {"data": {"name": "Duplicate Song", "artists": {"items": [{"profile": {"name": "Artist"}}]}}}},
            {"itemV2": {"data": {"name": "Duplicate Song 2", "artists": {"items": [{"profile": {"name": "Artist"}}]}}}},
        ],
    )
    mock_get_yt_pl.return_value = ("Test YT PL", [])
    # Search returns same video ID twice
    mock_search.return_value = (
        [("vid_dup", "Duplicate Song", "Artist"), ("vid_dup", "Duplicate Song 2", "Artist")],
        [],
    )
    mock_add.return_value = (1, 0)

    sync("spotify_123", "yt_123", preserve=False, dry_run=False)

    # add_in_batches should only receive 1 unique video ID
    mock_add.assert_called_once_with(mock_get_client.return_value, "yt_123", ["vid_dup"])
