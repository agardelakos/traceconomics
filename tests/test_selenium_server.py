"""The Selenium suite's static server (tests/selenium/server.py): the built site, and its one page of its own.

Standard library only, so it runs without the Selenium package.
"""

import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "selenium"))
import server  # noqa: E402

pytestmark = pytest.mark.unit


def test_the_blank_page_asks_for_nothing_and_the_site_is_served_as_built(tmp_path):
    """PY-SELSRV-001: the server's blank page runs nothing and names an empty icon; the build is served as it is

    Given a built site of one page
    When the server is asked for the blank page, the page, and a favicon.ico the site doesn't have
    Then the blank page is HTML with an empty icon and no script, so a browser asks for nothing more
    And the site's page comes back as built, never to be cached
    And the missing file is a 404, as on the host
    """
    (tmp_path / "index.html").write_text("<!DOCTYPE html><title>site</title>", encoding="utf-8")
    with server.StaticServer(tmp_path) as srv:
        with urllib.request.urlopen(srv.url + server.BLANK, timeout=5) as r:
            blank = r.read().decode("utf-8")
            assert r.headers["Content-Type"].startswith("text/html")
        with urllib.request.urlopen(srv.url + "/", timeout=5) as r:
            assert r.read() == (tmp_path / "index.html").read_bytes()
            assert r.headers["Cache-Control"] == "no-store"
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(srv.url + "/favicon.ico", timeout=5)
        assert e.value.code == 404
    assert '<link rel="icon" href="data:,">' in blank and "<script" not in blank
