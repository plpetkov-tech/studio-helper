"""Single-instance handoff via instance.json (SPEC.md §6.2).

On startup, if instance.json names a server that answers /api/health
with a matching token, we hand off to it (open the browser there and
exit) instead of starting a second server.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from studio_helper import paths


@dataclass
class InstanceInfo:
    port: int
    token: str
    pid: int

    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#token={self.token}"


def read() -> InstanceInfo | None:
    path = paths.instance_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return InstanceInfo(port=data["port"], token=data["token"], pid=data["pid"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None


def write(info: InstanceInfo) -> None:
    paths.ensure_app_data_dirs()
    paths.instance_path().write_text(json.dumps(asdict(info)), encoding="utf-8")


def clear() -> None:
    try:
        paths.instance_path().unlink()
    except FileNotFoundError:
        pass


def is_alive(info: InstanceInfo, timeout: float = 1.0) -> bool:
    req = urllib.request.Request(
        f"http://127.0.0.1:{info.port}/api/health",
        headers={"X-Studio-Helper-Token": info.token, "Host": f"127.0.0.1:{info.port}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def find_live_instance() -> InstanceInfo | None:
    info = read()
    if info is not None and is_alive(info):
        return info
    return None
