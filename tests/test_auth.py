import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spotiyt.auth import refresh_from_cookies_json


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cookies_path = Path(self.temp_dir.name) / "cookies.json"
        self.auth_path = Path(self.temp_dir.name) / "auth.json"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_missing_cookies_file_returns_false(self):
        result = refresh_from_cookies_json(self.cookies_path, self.auth_path)
        self.assertFalse(result)

    def test_invalid_json_returns_false(self):
        self.cookies_path.write_text("invalid json content")
        result = refresh_from_cookies_json(self.cookies_path, self.auth_path)
        self.assertFalse(result)

    def test_missing_sapisid_returns_false(self):
        self.cookies_path.write_text(json.dumps([{"name": "OTHER_COOKIE", "value": "123"}]))
        result = refresh_from_cookies_json(self.cookies_path, self.auth_path)
        self.assertFalse(result)

    @patch("spotiyt.auth.setup_browser")
    def test_valid_cookies_generates_auth(self, mock_setup_browser):
        cookies = [
            {"name": "SAPISID", "value": "sample_sapisid"},
            {"name": "SID", "value": "sample_sid"},
        ]
        self.cookies_path.write_text(json.dumps(cookies))
        result = refresh_from_cookies_json(self.cookies_path, self.auth_path)
        self.assertTrue(result)
        mock_setup_browser.assert_called_once()
        call_kwargs = mock_setup_browser.call_args.kwargs
        self.assertEqual(call_kwargs["filepath"], str(self.auth_path))
        self.assertIn("cookie: ", call_kwargs["headers_raw"])
        self.assertIn("authorization: SAPISIDHASH ", call_kwargs["headers_raw"])


if __name__ == "__main__":
    unittest.main()
