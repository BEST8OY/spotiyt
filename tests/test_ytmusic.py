from pathlib import Path
from unittest.mock import patch

import pytest

from spotiyt.ytmusic import get_ytmusic_client, import_to_ytmusic


def test_get_ytmusic_client_missing_file_raises(tmp_path: Path):
    non_existent = tmp_path / "non_existent_auth.json"
    with pytest.raises(FileNotFoundError):
        get_ytmusic_client(non_existent)


@patch("spotiyt.ytmusic.get_ytmusic_client")
def test_import_empty_csv_aborts(mock_get_client, tmp_path: Path):
    csv_file = tmp_path / "test_playlist.csv"
    csv_file.write_text("track_name,artists,album_name\n")
    res = import_to_ytmusic(str(csv_file), "Test Playlist")
    assert res == ""
    mock_get_client.return_value.create_playlist.assert_not_called()


@patch("spotiyt.ytmusic.get_ytmusic_client")
@patch("spotiyt.ytmusic.search_tracks")
def test_import_no_matched_tracks_aborts_without_creating_playlist(mock_search, mock_get_client, tmp_path: Path):
    csv_file = tmp_path / "test_playlist.csv"
    csv_file.write_text("track_name,artists,album_name\nTrack A,Artist A,Album A\n")
    mock_search.return_value = ([], [{"name": "Track A", "artists": "Artist A"}])

    res = import_to_ytmusic(str(csv_file), "Test Playlist")
    assert res == ""
    mock_get_client.return_value.create_playlist.assert_not_called()


@patch("spotiyt.ytmusic.get_ytmusic_client")
@patch("spotiyt.ytmusic.search_tracks")
@patch("spotiyt.ytmusic.add_in_batches")
@patch("spotiyt.ytmusic.verify_playlist")
def test_import_successful(mock_verify, mock_add, mock_search, mock_get_client, tmp_path: Path):
    csv_file = tmp_path / "test_playlist.csv"
    csv_file.write_text("track_name,artists,album_name\nTrack A,Artist A,Album A\n")
    mock_search.return_value = ([("vid_a", "Track A", "Artist A")], [])
    mock_get_client.return_value.create_playlist.return_value = "yt_playlist_123"
    mock_add.return_value = (1, 0)
    mock_verify.return_value = set()

    res = import_to_ytmusic(str(csv_file), "Test Playlist")
    assert res == "yt_playlist_123"
    mock_get_client.return_value.create_playlist.assert_called_once_with(
        title="Test Playlist", description="Imported from CSV"
    )
    mock_add.assert_called_once_with(mock_get_client.return_value, "yt_playlist_123", ["vid_a"])
