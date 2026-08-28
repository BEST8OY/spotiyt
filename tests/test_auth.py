import json
from pathlib import Path
from unittest.mock import patch

from spotiyt.auth import refresh_from_cookies_json


def test_missing_cookies_file_returns_false(tmp_path: Path):
    cookies_path = tmp_path / "cookies.json"
    auth_path = tmp_path / "auth.json"
    assert not refresh_from_cookies_json(cookies_path, auth_path)


def test_invalid_json_returns_false(tmp_path: Path):
    cookies_path = tmp_path / "cookies.json"
    auth_path = tmp_path / "auth.json"
    cookies_path.write_text("invalid json content")
    assert not refresh_from_cookies_json(cookies_path, auth_path)


def test_missing_sapisid_returns_false(tmp_path: Path):
    cookies_path = tmp_path / "cookies.json"
    auth_path = tmp_path / "auth.json"
    cookies_path.write_text(json.dumps([{"name": "OTHER_COOKIE", "value": "123"}]))
    assert not refresh_from_cookies_json(cookies_path, auth_path)


@patch("spotiyt.auth.setup_browser")
def test_valid_cookies_generates_auth(mock_setup_browser, tmp_path: Path):
    cookies_path = tmp_path / "cookies.json"
    auth_path = tmp_path / "auth.json"
    cookies = [
        {"name": "SAPISID", "value": "sample_sapisid"},
        {"name": "SID", "value": "sample_sid"},
    ]
    cookies_path.write_text(json.dumps(cookies))
    result = refresh_from_cookies_json(cookies_path, auth_path)
    assert result is True
    mock_setup_browser.assert_called_once()
    call_kwargs = mock_setup_browser.call_args.kwargs
    assert call_kwargs["filepath"] == str(auth_path)
    assert "cookie: " in call_kwargs["headers_raw"]
    assert "authorization: SAPISIDHASH " in call_kwargs["headers_raw"]
