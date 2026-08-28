import unittest

from spotiyt.ui import extract_spotify_id


class TestUIComponents(unittest.TestCase):
    def test_extract_spotify_id(self):
        # Full URL
        self.assertEqual(
            extract_spotify_id("https://open.spotify.com/playlist/37i9dQZF1E8MCNiiTgwMk8?si=123"),
            "37i9dQZF1E8MCNiiTgwMk8",
        )
        # URI
        self.assertEqual(extract_spotify_id("spotify:playlist:37i9dQZF1E8MCNiiTgwMk8"), "37i9dQZF1E8MCNiiTgwMk8")
        # Raw ID
        self.assertEqual(extract_spotify_id("37i9dQZF1E8MCNiiTgwMk8"), "37i9dQZF1E8MCNiiTgwMk8")
        # Invalid input
        self.assertIsNone(extract_spotify_id("not_a_valid_id!"))
        self.assertIsNone(extract_spotify_id(""))


if __name__ == "__main__":
    unittest.main()
