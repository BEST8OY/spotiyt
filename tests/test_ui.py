import pytest

from spotiyt.ui import extract_spotify_id


@pytest.mark.parametrize(
    ("input_val", "expected_id"),
    [
        ("https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8?si=123", "37i9dQZF1E8MCNiiTgwMk8"),
        ("spotify:playlist:37i9dQZF1E8MCNiiTgwMk8", "37i9dQZF1E8MCNiiTgwMk8"),
        ("37i9dQZF1E8MCNiiTgwMk8", "37i9dQZF1E8MCNiiTgwMk8"),
    ],
)
def test_extract_spotify_id_valid(input_val: str, expected_id: str):
    assert extract_spotify_id(input_val) == expected_id


@pytest.mark.parametrize(
    "invalid_input",
    [
        "not_a_valid_id!",
        "",
        "http://youtube.com/playlist?list=123",
    ],
)
def test_extract_spotify_id_invalid(invalid_input: str):
    assert extract_spotify_id(invalid_input) is None
