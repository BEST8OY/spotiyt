import pytest

from spotiyt.matching import _artist_ratio, clean, normalize_title


@pytest.mark.parametrize(
    ("a1", "a2"),
    [
        ("The Goo Goo Dolls", "Goo Goo Dolls"),
        ("Goo Goo Dolls", "The Goo Goo Dolls"),
        ("The Beatles", "Beatles"),
        ("The Weeknd", "Weeknd"),
    ],
)
def test_the_prefix_variations(a1: str, a2: str):
    assert _artist_ratio(a1, a2) >= 0.75


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Beyoncé", "beyonce"),
        ("Mötley Crüe", "motley crue"),
        ("Sigur Rós", "sigur ros"),
    ],
)
def test_clean_accents(raw: str, expected: str):
    assert clean(raw) == expected


@pytest.mark.parametrize(
    ("a1", "a2"),
    [
        ("Beyoncé", "Beyonce"),
        ("Mötley Crüe", "Motley Crue"),
        ("Lil Nas X; Jack Harlow", "Lil Nas X"),
        ("Eminem", "Eminem, Rihanna"),
        ("David Guetta x Bebe Rexha", "David Guetta & Bebe Rexha"),
        ("Artist A / Artist B", "Artist A, Artist B"),
        ("P!nk", "Pink"),
        ("Ke$ha", "Kesha"),
        ("AC/DC", "AC DC"),
        ("Panic! At The Disco", "Panic at the Disco"),
    ],
)
def test_artist_ratio_matching(a1: str, a2: str):
    assert _artist_ratio(a1, a2) >= 0.75


@pytest.mark.parametrize(
    ("raw_title", "expected_title"),
    [
        ("Iris - 2008 Remaster", "iris"),
        ("Iris (Official Music Video)", "iris"),
        ("Iris [Official Audio]", "iris"),
        ("Iris (Lyric Video)", "iris"),
        ("01. Iris", "iris"),
        ("Hotel California - 2013 Remaster", "hotel california"),
        ("Song Title (Radio Edit)", "song title"),
        ("Song Title (feat. Artist B)", "song title"),
        ("Song Title - Single Version", "song title"),
    ],
)
def test_title_stripping_and_normalization(raw_title: str, expected_title: str):
    assert normalize_title(raw_title) == expected_title


def test_unrelated_artists():
    assert _artist_ratio("Dua Lipa", "Taylor Swift") < 0.5
    assert _artist_ratio("Metallica", "Coldplay") < 0.5
