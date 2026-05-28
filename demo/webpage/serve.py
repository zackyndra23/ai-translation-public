"""Tiny static file server for the SDK demo webpage.

Run with::

    uv run python demo/webpage/serve.py

Serves ``demo/webpage/`` at http://localhost:8001/ AND proxies ``/sdk/*``
URLs to the project's ``sdk/`` directory so the demo page's
``<script src="/sdk/src/translator.js">`` works without a symlink.

We use the stdlib HTTP server instead of nginx / a bundler because the
demo's reason for existing is "see the SDK work end to end with the API
running on 8000" — adding a build step would defeat the demo's claim that
the SDK is drop-in standalone JS.
"""

from __future__ import annotations

import http.server
import socketserver
import sys
from pathlib import Path
from typing import Any

PORT = 8001

# Resolve the two roots once so per-request logic stays simple. ``WEBPAGE_DIR``
# is the static html root; ``SDK_DIR`` is the JS root that ``/sdk/*`` URLs
# resolve into. Both are inside the repo so the security check below has a
# tight boundary to enforce.
WEBPAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = WEBPAGE_DIR.parent.parent
SDK_DIR = REPO_ROOT / "sdk"

# Content types we know about — keeping this small avoids depending on the
# stdlib mimetypes module for the JS demo. Anything not listed falls
# through to SimpleHTTPRequestHandler's defaults.
_EXTRA_MIME = {
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
}


class DemoHandler(http.server.SimpleHTTPRequestHandler):
    """Serve ``demo/webpage/`` with a ``/sdk/*`` passthrough to ``sdk/``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEBPAGE_DIR), **kwargs)

    def do_GET(self) -> None:  # base class spelling; renaming would break the dispatch
        # ``/sdk/...`` is rewritten to a path under the repo's sdk/ dir.
        # We compute the requested path on disk and refuse anything that
        # tries to escape the SDK root (path-traversal defence).
        if self.path.startswith("/sdk/"):
            rel = self.path.removeprefix("/sdk/")
            target = (SDK_DIR / rel).resolve()
            try:
                target.relative_to(SDK_DIR.resolve())
            except ValueError:
                self.send_error(403, "Path traversal blocked")
                return
            if not target.exists() or not target.is_file():
                self.send_error(404, "SDK file not found")
                return
            self._serve_file(target)
            return

        # Everything else falls through to the default static-file logic.
        super().do_GET()

    def _serve_file(self, path: Path) -> None:
        content = path.read_bytes()
        mime = _EXTRA_MIME.get(path.suffix) or self.guess_type(str(path))
        # No-cache so the developer can iterate on the SDK without fighting
        # the browser's cache. Production deployments would set Cache-Control
        # more aggressively here.
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)


def main() -> int:
    # ``ThreadingHTTPServer`` keeps the page responsive when the browser
    # asks for sdk/ assets in parallel with html/css — the default
    # ``TCPServer`` handles requests one at a time, which under Chrome's
    # request fanout produces noticeable stalls.
    with socketserver.ThreadingTCPServer(("", PORT), DemoHandler) as httpd:
        print(f"Serving demo webpage on http://localhost:{PORT}")
        print(f"  static root : {WEBPAGE_DIR}")
        print(f"  /sdk/*      : -> {SDK_DIR}")
        print("  Ctrl-C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
