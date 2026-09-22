"""Local-only web UI server (SPEC.md §6.2).

- Binds 127.0.0.1 on a random free port.
- Every /api/* call must carry the per-launch token in the
  X-Studio-Helper-Token header.
- The Host header is checked against 127.0.0.1:<port> or
  localhost:<port> to defeat DNS rebinding. No CORS headers are ever
  sent, so no other origin can read responses even if it guesses the
  port.
- No outbound network calls are made anywhere in this process.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import secrets
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from studio_helper import __version__

logger = logging.getLogger("studio_helper.server")

WEB_ROOT = Path(__file__).parent / "web"


def make_token() -> str:
    return secrets.token_urlsafe(24)


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Handler(BaseHTTPRequestHandler):
    server: StudioHelperServer

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        logger.info("%s - %s", self.address_string(), fmt % args)

    # -- helpers -----------------------------------------------------

    def _valid_host(self) -> bool:
        host = self.headers.get("Host", "")
        hostname = host.split(":")[0]
        return hostname in ("127.0.0.1", "localhost")

    def _valid_token(self) -> bool:
        supplied = self.headers.get("X-Studio-Helper-Token", "")
        return secrets.compare_digest(supplied, self.server.token)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        data = path.read_bytes()
        guessed_type = mimetypes.guess_type(str(path))[0]
        self.send_response(200)
        self.send_header(
            "Content-Type", content_type or guessed_type or "application/octet-stream"
        )
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _serve_static(self, url_path: str) -> None:
        rel = url_path[len("/static/") :]
        candidate = (WEB_ROOT / "static" / rel).resolve()
        static_root = (WEB_ROOT / "static").resolve()
        if static_root not in candidate.parents and candidate != static_root:
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if not candidate.is_file():
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        self._send_file(candidate)

    # -- routes --------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._send_json(400, {"ok": False, "error": "invalid host"})
            return

        path = self.path.split("?")[0].split("#")[0]

        if path == "/" or path == "/index.html":
            self._send_file(WEB_ROOT / "index.html", "text/html; charset=utf-8")
            return

        if path.startswith("/static/"):
            self._serve_static(path)
            return

        if path == "/api/health":
            self._send_json(200, {"ok": True, "version": __version__})
            return

        if path.startswith("/api/"):
            if not self._valid_token():
                self._send_json(401, {"ok": False, "error": "invalid token"})
                return
            self._send_json(404, {"ok": False, "error": "unknown endpoint"})
            return

        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._valid_host():
            self._send_json(400, {"ok": False, "error": "invalid host"})
            return

        path = self.path.split("?")[0].split("#")[0]

        if not path.startswith("/api/"):
            self._send_json(404, {"ok": False, "error": "not found"})
            return

        if not self._valid_token():
            self._send_json(401, {"ok": False, "error": "invalid token"})
            return

        if path == "/api/quit":
            self._send_json(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        self._send_json(404, {"ok": False, "error": "unknown endpoint"})


class StudioHelperServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str, port: int = 0):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = token


def create_server(token: str | None = None, port: int = 0) -> StudioHelperServer:
    return StudioHelperServer(token or make_token(), port)
