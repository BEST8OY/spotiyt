import unittest

from spotiyt.matching import (
    _artist_ratio,
    clean,
    normalize_title,
)


class TestMatchingLogic(unittest.TestCase):
    def test_the_prefix_variations(self):
        # 'The Goo Goo Dolls' vs 'Goo Goo Dolls'
        self.assertGreaterEqual(_artist_ratio("The Goo Goo Dolls", "Goo Goo Dolls"), 0.75)
        self.assertGreaterEqual(_artist_ratio("Goo Goo Dolls", "The Goo Goo Dolls"), 0.75)

        # 'The Beatles' vs 'Beatles'
        self.assertGreaterEqual(_artist_ratio("The Beatles", "Beatles"), 0.75)

        # 'The Weeknd' vs 'Weeknd'
        self.assertGreaterEqual(_artist_ratio("The Weeknd", "Weeknd"), 0.75)

    def test_accents_and_diacritics(self):
        self.assertEqual(clean("Beyoncé"), "beyonce")
        self.assertEqual(clean("Mötley Crüe"), "motley crue")
        self.assertEqual(clean("Sigur Rós"), "sigur ros")
        self.assertGreaterEqual(_artist_ratio("Beyoncé", "Beyonce"), 0.75)
        self.assertGreaterEqual(_artist_ratio("Mötley Crüe", "Motley Crue"), 0.75)

    def test_multi_artist_delimiters(self):
        # Spotify has Lil Nas X; Jack Harlow, YouTube has Lil Nas X
        self.assertGreaterEqual(_artist_ratio("Lil Nas X; Jack Harlow", "Lil Nas X"), 0.75)
        # Spotify has Eminem, YouTube has Eminem, Rihanna
        self.assertGreaterEqual(_artist_ratio("Eminem", "Eminem, Rihanna"), 0.75)
        # Conjunctions: x vs &
        self.assertGreaterEqual(_artist_ratio("David Guetta x Bebe Rexha", "David Guetta & Bebe Rexha"), 0.75)
        # Slash vs comma
        self.assertGreaterEqual(_artist_ratio("Artist A / Artist B", "Artist A, Artist B"), 0.75)

    def test_stylistic_and_punctuated_artists(self):
        # P!nk vs Pink
        self.assertGreaterEqual(_artist_ratio("P!nk", "Pink"), 0.75)
        # Ke$ha vs Kesha
        self.assertGreaterEqual(_artist_ratio("Ke$ha", "Kesha"), 0.75)
        # AC/DC vs AC DC
        self.assertGreaterEqual(_artist_ratio("AC/DC", "AC DC"), 0.75)
        # Panic! At The Disco vs Panic at the Disco
        self.assertGreaterEqual(_artist_ratio("Panic! At The Disco", "Panic at the Disco"), 0.75)

    def test_title_stripping_and_normalization(self):
        self.assertEqual(normalize_title("Iris - 2008 Remaster"), "iris")
        self.assertEqual(normalize_title("Iris (Official Music Video)"), "iris")
        self.assertEqual(normalize_title("Iris [Official Audio]"), "iris")
        self.assertEqual(normalize_title("Iris (Lyric Video)"), "iris")
        self.assertEqual(normalize_title("01. Iris"), "iris")
        self.assertEqual(normalize_title("Hotel California - 2013 Remaster"), "hotel california")
        self.assertEqual(normalize_title("Song Title (Radio Edit)"), "song title")
        self.assertEqual(normalize_title("Song Title (feat. Artist B)"), "song title")
        self.assertEqual(normalize_title("Song Title - Single Version"), "song title")

    def test_unrelated_artists(self):
        self.assertLess(_artist_ratio("Dua Lipa", "Taylor Swift"), 0.5)
        self.assertLess(_artist_ratio("Metallica", "Coldplay"), 0.5)


if __name__ == "__main__":
    unittest.main()
