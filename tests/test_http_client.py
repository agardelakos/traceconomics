"""The polite HTTP client and the run context every source adapter shares, against a local server.

The server runs on 127.0.0.1 and answers from a script: each path has a list of responses, served
in order (the last one repeats). Waits are recorded rather than slept, so the pauses the client
keeps between requests are checked at their real lengths without slowing the run."""

import threading
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from traceconomics.archive.store import Archive
from traceconomics.sources import base
from traceconomics.sources.base import FetchError, HttpClient, Response, RunContext, guess_ext

pytestmark = pytest.mark.integration

ALLOW_ALL = (200, {}, b"User-agent: *\nDisallow:\n")


@pytest.fixture
def server():
    """(base URL, script, log): set script[path] to a list of (status, headers, body); log lists
    (path, User-Agent) for every request received."""
    script, log = {"/robots.txt": [ALLOW_ALL]}, []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            log.append((self.path, self.headers.get("User-Agent")))
            answers = script.get(self.path, [(404, {}, b"not here")])
            status, headers, body = answers.pop(0) if len(answers) > 1 else answers[0]
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    # A short poll interval: shutdown waits for the next poll, half a second by default.
    threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}", script, log
    httpd.shutdown()


@pytest.fixture
def waits(monkeypatch):
    """Every time.sleep the client asks for, in seconds, instead of sleeping."""
    asked = []
    monkeypatch.setattr(base.time, "sleep", asked.append)
    return asked


def test_a_download_is_streamed_to_a_file_with_the_headers_worth_keeping(server, waits, tmp_path):
    """PY-HTTP-001: a download is streamed to a file, keeping only the headers worth keeping

    Given a server whose robots.txt allows everything
    And a file served with a content type, a content disposition naming "../Table 07.XLSX", a date and a cookie
    When the client downloads it, and downloads it again
    Then the file holds the served bytes and the response has status 200
    And only the kept headers are recorded, not the cookie
    And the file name is "Table 07.XLSX", without the path
    And every request carries the project's User-Agent
    And robots.txt is read once for the host
    And the second request waits the full pause after the first
    """
    url, script, log = server
    script["/t07"] = [
        (
            200,
            {
                "Content-Type": "application/vnd.ms-excel",
                "Set-Cookie": "id=1",
                "Content-Disposition": 'attachment; filename="../Table 07.XLSX"',
            },
            b"payload",
        )
    ]
    client = HttpClient("traceconomics-test", pause_seconds=2.0)
    resp = client.download(url + "/t07", tmp_path / "f")
    assert (tmp_path / "f").read_bytes() == b"payload" and resp.status == 200
    assert set(resp.headers) <= set(base.KEPT_HEADERS) and "set-cookie" not in resp.headers
    assert resp.headers["content-type"] == "application/vnd.ms-excel"
    assert resp.filename == "Table 07.XLSX"
    client.download(url + "/t07", tmp_path / "f")
    assert [p for p, _ in log] == ["/robots.txt", "/t07", "/t07"]
    assert {ua for _, ua in log} == {"traceconomics-test"}
    assert waits and waits[-1] == pytest.approx(2.0, abs=0.2)


def test_robots_txt_is_respected(server, waits, tmp_path):
    """PY-HTTP-002: a path robots.txt disallows is never requested

    Given a server whose robots.txt disallows /private/ for every agent
    When the client downloads /private/data
    Then it raises a FetchError saying robots.txt disallows it
    And only robots.txt was requested
    """
    url, script, log = server
    script["/robots.txt"] = [(200, {}, b"User-agent: *\nDisallow: /private/\n")]
    with pytest.raises(FetchError, match="disallowed by robots.txt"):
        HttpClient("t", pause_seconds=0).download(url + "/private/data", tmp_path / "f")
    assert [p for p, _ in log] == ["/robots.txt"]


@pytest.mark.parametrize("robots, fetched", [(404, True), (500, False)])
def test_a_missing_robots_txt_allows_everything_but_a_broken_one_stops(server, waits, tmp_path, robots, fetched):
    """PY-HTTP-003: no robots.txt means no restrictions, but a server error on it stops the fetch

    Given a server whose robots.txt answers 404 or 500
    When the client downloads a file
    Then with 404 the file is fetched
    And with 500 a FetchError names robots.txt and the file is never requested
    """
    url, script, log = server
    script["/robots.txt"] = [(robots, {}, b"")]
    script["/f"] = [(200, {}, b"x")]
    client = HttpClient("t", pause_seconds=0)
    if fetched:
        client.download(url + "/f", tmp_path / "f")
        assert (tmp_path / "f").read_bytes() == b"x"
    else:
        with pytest.raises(FetchError, match="robots.txt"):
            client.download(url + "/f", tmp_path / "f")
        assert [p for p, _ in log] == ["/robots.txt"]


def test_an_unreachable_host_is_a_fetch_error(tmp_path, waits):
    """PY-HTTP-004: a host that can't be reached is a FetchError, not a crash

    Given a local port nothing listens on
    When the client downloads from it
    Then it raises a FetchError naming robots.txt, the first thing it asks for
    """
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    with pytest.raises(FetchError, match="robots.txt"):
        HttpClient("t", pause_seconds=0).download(f"http://127.0.0.1:{port}/f", tmp_path / "f")


@pytest.mark.parametrize("first", [503, 429])
def test_a_server_error_or_rate_limit_is_retried_with_growing_waits(server, waits, tmp_path, first):
    """PY-HTTP-005: a server error or a rate limit is retried, waiting longer each time

    Given a file that answers 503 (or 429) twice, then 200
    And a client with a 2-second pause and three tries
    When the client downloads it
    Then it gets the file on the third try
    And it waited 10 seconds before the second try and 20 before the third
    """
    url, script, log = server
    script["/f"] = [(first, {}, b""), (first, {}, b""), (200, {}, b"ok")]
    HttpClient("t", pause_seconds=2.0, retries=3).download(url + "/f", tmp_path / "f")
    assert (tmp_path / "f").read_bytes() == b"ok"
    assert [p for p, _ in log].count("/f") == 3
    assert 10.0 in waits and 20.0 in waits


def test_a_client_error_is_not_retried_and_leaves_no_file(server, waits, tmp_path):
    """PY-HTTP-006: a client error is not retried, and no partial file is left

    Given a file that answers 404
    When the client downloads it
    Then it raises a FetchError naming the URL and the error
    And it asked only once
    And no file is left at the destination
    """
    url, script, log = server
    script["/gone"] = [(404, {}, b"")]
    with pytest.raises(FetchError, match=r"/gone: HTTP Error 404"):
        HttpClient("t", pause_seconds=0).download(url + "/gone", tmp_path / "f")
    assert [p for p, _ in log].count("/gone") == 1
    assert not (tmp_path / "f").exists()


def test_a_server_error_on_every_try_gives_up(server, waits, tmp_path):
    """PY-HTTP-007: a server error on every try gives up after the last one

    Given a file that always answers 500
    When a client with three tries downloads it
    Then it asks three times and raises a FetchError with the last error
    """
    url, script, log = server
    script["/f"] = [(500, {}, b"")]
    with pytest.raises(FetchError, match="HTTP Error 500"):
        HttpClient("t", pause_seconds=0, retries=3).download(url + "/f", tmp_path / "f")
    assert [p for p, _ in log].count("/f") == 3


def test_get_bytes_returns_the_body_and_cleans_up(server, waits, tmp_path):
    """PY-HTTP-008: get_bytes returns the body and removes its temporary file

    Given a small file on the server
    When the client gets its bytes through a temporary file
    Then the bytes are returned with the response
    And the temporary file is gone
    """
    url, script, _ = server
    script["/small"] = [(200, {"Content-Type": "text/plain"}, b"hello")]
    resp, data = HttpClient("t", pause_seconds=0).get_bytes(url + "/small", tmp_path / "tmp")
    assert data == b"hello" and resp.headers["content-type"] == "text/plain"
    assert not (tmp_path / "tmp").exists()


def _resp(**headers):
    return Response("u", 200, headers, datetime(2026, 1, 1, tzinfo=UTC))


@pytest.mark.parametrize(
    "headers, ext",
    [
        ({"content-disposition": 'attachment; filename="A.XLSX"'}, ".xlsx"),
        ({"content-disposition": "attachment; filename=noext", "content-type": "text/html"}, ".html"),
        ({"content-type": "application/json; charset=utf-8"}, ".json"),
        ({"content-type": "application/x-gzip"}, ".gz"),
        ({"content-type": "application/octet-stream"}, ""),
        ({}, ""),
    ],
)
def test_the_extension_comes_from_the_file_name_else_the_content_type(headers, ext):
    """PY-HTTP-009: a download's extension comes from its file name, else from its content type

    Given a response with or without a file name and a content type
    When its extension is guessed
    Then a file name's extension wins, lower-cased
    And without one, a known content type gives its extension, parameters ignored
    And an unknown content type, or none, gives no extension
    """
    assert guess_ext(_resp(**headers)) == ext


def test_a_response_without_a_disposition_has_no_file_name():
    """PY-HTTP-010: a response without a content disposition has no file name

    Given a response with no Content-Disposition, and one whose disposition names no file
    When their file names are read
    Then both are None
    And the manifest of the response holds its status and headers
    """
    assert _resp().filename is None and _resp(**{"content-disposition": "inline"}).filename is None
    assert _resp(**{"content-type": "text/html"}).manifest() == {
        "status": 200,
        "headers": {"content-type": "text/html"},
    }


def test_the_run_context_stores_what_it_fetches_and_logs_what_fails(server, waits, tmp_path):
    """PY-HTTP-011: the run context stores each download once, judged by its content, and logs failures

    Given a page served with a file name, then served again with only an invisible change
    And a path that answers 404
    When the run context fetches the page with a content rule that ignores the invisible part, twice
    And fetches the missing path
    And plans a fetch as a dry run
    Then the first fetch stores the page with the server's file name as its original name and its extension
    And the second fetch finds it unchanged
    And the failed fetch is in the context's failures and the archive's log, and stores nothing
    And the dry run only lists the fetch it would make
    """
    url, script, _ = server
    disposition = {"Content-Disposition": 'attachment; filename="page.HTML"'}
    script["/page"] = [(200, disposition, b"<p>text</p><!--1-->"), (200, disposition, b"<p>text</p><!--2-->")]
    archive = Archive(tmp_path / "archive")
    ctx = RunContext(archive=archive, http=HttpClient("t", pause_seconds=0), today=date(2026, 11, 7))
    visible = lambda data: data.split(b"<!--")[0].decode()  # noqa: E731
    first, data = ctx.fetch_and_store("src", "page", url + "/page", content_of=visible)
    assert first.status == "stored" and data == b"<p>text</p><!--1-->"
    assert archive.manifest(archive.latest("src", "page"))["original_name"] == "page.HTML"
    assert first.path.suffix == ".html"
    second, _ = ctx.fetch_and_store("src", "page", url + "/page", content_of=visible)
    assert second.status == "unchanged"
    assert ctx.fetch_and_store("src", "gone", url + "/gone") == (None, None)
    assert len(ctx.failures) == 1 and ctx.failures[0].startswith("src/gone: ")
    assert any(r.get("status") == "failed" and r.get("dataset") == "gone" for r in archive.index())
    dry = RunContext(archive=archive, http=HttpClient("t"), today=date(2026, 11, 7), dry_run=True)
    assert dry.fetch_and_store("src", "x", "https://example.invalid/x") == (None, None)
    assert dry.planned == ["src/x: https://example.invalid/x"]
