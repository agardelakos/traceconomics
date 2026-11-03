"""A static server for the built site, in a thread of the test process.

It serves `site/dist` the way a static host does: `/en/about/` is `en/about/index.html`, a folder
without its slash is redirected to it, anything missing is a 404. It sends none of the host's own
headers (`site/public/_headers`): the tests that check those run against a real host (`--base-url`).
"""

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".js": "text/javascript",
        ".mjs": "text/javascript",
        ".json": "application/json",
        ".svg": "image/svg+xml",
        ".csv": "text/csv",
        ".parquet": "application/vnd.apache.parquet",
        ".txt": "text/plain; charset=utf-8",
        ".xml": "application/xml",
    }

    def end_headers(self):
        # Every test sees the current build, never a cached copy from an earlier one.
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        pass  # quiet: the browser's own log is what the tests read


class StaticServer:
    def __init__(self, root: Path):
        if not (root / "index.html").is_file():
            raise FileNotFoundError(f"{root} holds no built site: run `npm run build` in site/ first")
        handler = partial(_Handler, directory=str(root))
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self._httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self._httpd.server_address[1]}"
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._httpd.shutdown()
        self._httpd.server_close()
