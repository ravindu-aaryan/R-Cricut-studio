"""The interface must not reference remote resources (fonts, scripts, CDNs, analytics)."""
from scripts import verify_offline


def test_repository_has_no_remote_references():
    assert verify_offline.static_check() == []


def test_scanner_detects_remote_urls():
    for bad in ('<script src="https://cdn.example.com/x.js">', "@import url(//fonts.example.com/css);", "fetch('http://api.example.org/v1')"):
        assert verify_offline.URL_RE.search(bad), bad
    assert verify_offline.CLIENT_IMPORTS.search("import requests\n")
    assert not verify_offline.CLIENT_IMPORTS.search("import json\n")
