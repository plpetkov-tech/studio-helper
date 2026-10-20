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
import re
import secrets
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

from studio_helper import __version__
from studio_helper.api import dispatch

logger = logging.getLogger("studio_helper.server")

WEB_ROOT = Path(__file__).parent / "web"

# Windows reads these from the registry, where they can be missing or
# wrong (.js as text/plain gets blocked under nosniff) -- pin them.
for _type, _ext in (("text/css", ".css"), ("text/javascript", ".js"), ("font/woff2", ".woff2"),
                    ("video/mp4", ".mp4"), ("video/quicktime", ".mov")):
    mimetypes.add_type(_type, _ext)

# Files a job page may show (video masters, brand pieces, exports), and
# uploads (masters, pieces), always inside the job's own folder.
JOB_FILE = re.compile(r"^/api/jobs/([^/]+)/file$")
JOB_UPLOAD = re.compile(r"^/api/jobs/([^/]+)/upload$")
VIEWABLE_DIRS = ("02_assets/", "04_export/")
MAX_UPLOAD_BYTES = 4 * 1024**3
CHUNK = 1024 * 1024

# Fixed whitelist, never derived from the request path (SPEC.md §8 path safety).
PAGES = {
    "/": "index.html",
    "/index.html": "index.html",
    "/new-job.html": "new-job.html",
    "/job.html": "job.html",
    "/formats.html": "formats.html",
    "/registry.html": "formats.html",  # old bookmark
    "/setup-check.html": "setup-check.html",
    "/guide.html": "guide.html",
}


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

    def _valid_token(self, allow_query: bool = False) -> bool:
        supplied = self.headers.get("X-Studio-Helper-Token", "")
        if not supplied and allow_query:
            # <video src> can't send headers: file views carry it as ?t=
            supplied = self._query().get("t", "")
        return secrets.compare_digest(supplied, self.server.token)

    def _query(self) -> dict[str, str]:
        raw = self.path.split("?", 1)[1] if "?" in self.path else ""
        return {k: v[0] for k, v in parse_qs(raw.split("#")[0]).items()}

    def _job_root(self, job_id: str) -> Path | None:
        from studio_helper.core import job as job_mod
        try:
            root = job_mod.job_path(self.server.ctx.jobs_root, job_id)
        except job_mod.JobError:
            return None
        return root if (root / "job.json").is_file() else None

    def _serve_job_file(self, job_id: str) -> None:
        """Streams a file from the job's assets or exports, with Range
        support so the browser's video player can seek."""
        root = self._job_root(job_id)
        rel = self._query().get("rel", "")
        if root is None or not rel.startswith(VIEWABLE_DIRS):
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        target = (root / rel).resolve()
        if root.resolve() not in target.parents or not target.is_file():
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        size = target.stat().st_size
        start, end = 0, size - 1
        m = re.match(r"bytes=(\d*)-(\d*)$", self.headers.get("Range", ""))
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(size - int(m.group(2)), 0)
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0]
                         or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        with target.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(CHUNK, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return  # the player moved on (seeking); fine
                left -= len(chunk)

    def _receive_upload(self, job_id: str, path: str) -> None:
        """A raw file (drag and drop) streamed to a temporary file inside
        the job folder, then handed to the API to put in place."""
        root = self._job_root(job_id)
        length = int(self.headers.get("Content-Length", 0) or 0)
        if root is None:
            self._send_json(404, {"ok": False, "error": "No such job."})
            return
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            self._send_json(400, {"ok": False, "error": "That file is empty or over 4 GB."})
            return
        tmp_dir = root / ".uploads"
        tmp_dir.mkdir(exist_ok=True)
        tmp = tmp_dir / f"{uuid.uuid4().hex}.part"
        try:
            with tmp.open("wb") as f:
                left = length
                while left > 0:
                    chunk = self.rfile.read(min(CHUNK, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left:
                self._send_json(400, {"ok": False, "error": "The upload was cut off."})
                return
            body = dict(self._query(), tmp=str(tmp))
            status, payload = dispatch("POST", path, self.server.ctx, body)
            self._send_json(status, payload)
        finally:
            tmp.unlink(missing_ok=True)

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

        if path in PAGES:
            self._send_file(WEB_ROOT / PAGES[path], "text/html; charset=utf-8")
            return

        if path.startswith("/static/"):
            self._serve_static(path)
            return

        if path == "/api/health":
            self._send_json(200, {"ok": True, "version": __version__})
            return

        job_file = JOB_FILE.match(path)
        if job_file and self.server.ctx is not None:
            if not self._valid_token(allow_query=True):
                self._send_json(401, {"ok": False, "error": "invalid token"})
                return
            self._serve_job_file(job_file.group(1))
            return

        if path.startswith("/api/"):
            if not self._valid_token():
                self._send_json(401, {"ok": False, "error": "invalid token"})
                return
            if self.server.ctx is None:
                self._send_json(500, {"ok": False, "error": "server not configured"})
                return
            status, payload = dispatch("GET", path, self.server.ctx, None)
            self._send_json(status, payload)
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

        if self.server.ctx is None:
            self._send_json(500, {"ok": False, "error": "server not configured"})
            return

        upload = JOB_UPLOAD.match(path)
        if upload and self.headers.get("Content-Type", "").startswith("application/octet-stream"):
            self._receive_upload(upload.group(1), path)
            return

        try:
            body = self._read_json_body()
        except ValueError:
            self._send_json(400, {"ok": False, "error": "invalid JSON body"})
            return

        status, payload = dispatch("POST", path, self.server.ctx, body)
        self._send_json(status, payload)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))


class StudioHelperServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, token: str, port: int = 0, ctx=None):
        super().__init__(("127.0.0.1", port), Handler)
        self.token = token
        self.ctx = ctx


def create_server(token: str | None = None, port: int = 0, ctx=None) -> StudioHelperServer:
    return StudioHelperServer(token or make_token(), port, ctx)
