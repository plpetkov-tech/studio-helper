"""Talks to her own Concat install over MCP (ROADMAP R5).

Concat is AGPL, so it is never bundled: she installs it herself, and this
module starts `concat --mcp headless` as a separate program and speaks
newline-delimited JSON-RPC to it over stdin/stdout. Every write Concat
makes is confined to CONCAT_MCP_ROOTS, which is set to the jobs folder.

One ConcatSession per task thread, never shared; Concat itself renders
one export at a time.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# The version this code was written and tested against. A newer one gets
# a gentle warning in Setup check, never a block.
TESTED_CONCAT_VERSION = "0.2.8"
PROTOCOL_VERSION = "2025-06-18"
CALL_TIMEOUT_S = 60

# Tools and the argument names we send. Checked against tools/list on
# start, so a Concat update that renames something fails with a plain
# message instead of half-way through a render.
TOOLS_USED = {
    "concat_version": set(),
    "project_create": {"location", "name", "video"},
    "project_open": {"path"},
    "project_save": {"path"},
    "project_close": {"path", "save"},
    "media_import": {"path", "file"},
    "media_probe": {"path"},
    "timeline_read": {"path"},
    "track_add": {"path", "bottom"},
    "clip_add": {"path", "mediaId", "trackId", "start"},
    "clip_transform": {"path", "clipId", "scale", "offsetX", "offsetY"},
    "clip_trim": {"path", "clipId", "edge", "delta"},
    "clip_update": {"path", "clipId", "patch"},
    "keyframe_set": {"path", "clipId", "property", "at", "value", "ease"},
    "timeline_background": {"path", "timelineId", "background"},
    "export_start": {"path", "output", "crf", "width", "height", "rateNum", "rateDen", "codec"},
    "export_wait": {"job", "timeoutSeconds"},
    "export_cancel": {"job"},
    "preview_frame": {"path", "time", "output", "width", "height"},
}


class ConcatError(Exception):
    """A plain-language problem with Concat, safe to show her."""


def find_concat(configured: str | None = None) -> Path | None:
    """Settings override, then the per-user and all-users installs, then
    PATH (Linux development)."""
    candidates = []
    if configured:
        candidates.append(Path(configured))
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        if local:
            candidates.append(Path(local) / "Programs" / "Concat" / "concat.exe")
        for env in ("ProgramFiles", "ProgramW6432"):
            base = os.environ.get(env)
            if base:
                candidates.append(Path(base) / "Concat" / "concat.exe")
    for c in candidates:
        if c.is_file():
            return c
    found = shutil.which("concat")
    return Path(found) if found else None


def _friendly(message: str, code: str | None) -> str:
    if code == "refused" and "open in" in message:
        return ("This video project is open in Concat. Close it in Concat first, "
                "then try again.")
    if code == "busy":
        return "Concat is exporting something else; try again when it has finished."
    return message


class ConcatSession:
    """`with ConcatSession(roots=[jobs_root]) as c: c.call("project_create", ...)`"""

    def __init__(self, roots: list[Path], exe: Path | None = None, env: dict | None = None,
                 command: list[str] | None = None):
        # `command` replaces the whole command line (tests run a fake Concat)
        self.command = command
        self.exe = exe or (None if command else find_concat())
        if self.exe is None and not command:
            raise ConcatError("Concat isn't installed. Install it (free, concatenate.pages.dev), "
                              "then try again.")
        self.roots = [Path(r) for r in roots]
        self.extra_env = env or {}
        self.version: str | None = None
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue = queue.Queue()
        self._next_id = 0
        self._opened: set[str] = set()

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> ConcatSession:
        env = dict(os.environ, **self.extra_env)
        env["CONCAT_MCP_ROOTS"] = os.pathsep.join(str(r) for r in self.roots)
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            self._proc = subprocess.Popen(
                self.command or [str(self.exe), "--mcp", "headless"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=env, creationflags=flags, encoding="utf-8",
            )
        except OSError as exc:
            raise ConcatError(f"Couldn't start Concat: {exc}. Check Setup check.") from exc
        threading.Thread(target=self._read, daemon=True).start()
        self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION, "capabilities": {},
            "clientInfo": {"name": "studio-helper", "version": "1"},
        })
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self._check_tools(self._request("tools/list", {}).get("tools", []))
        self.version = (self.call("concat_version") or {}).get("concat")
        return self

    def __exit__(self, *exc) -> None:
        for path in list(self._opened):
            try:
                self.call("project_close", path=path, save=False)
            except Exception:  # noqa: BLE001 - closing down anyway
                pass
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                self._proc.kill()

    # -- protocol -----------------------------------------------------------

    def _read(self) -> None:
        for line in self._proc.stdout:
            line = line.strip()
            if line:
                try:
                    self._lines.put(json.loads(line))
                except ValueError:
                    logger.warning("Concat sent a non-JSON line: %.200s", line)
        self._lines.put(None)

    def _send(self, msg: dict) -> None:
        try:
            self._proc.stdin.write(json.dumps(msg) + "\n")
            self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise ConcatError("Concat stopped unexpectedly.") from exc

    def _request(self, method: str, params: dict, timeout: float = CALL_TIMEOUT_S,
                 on_progress: Callable[[dict], None] | None = None) -> dict:
        self._next_id += 1
        my_id = self._next_id
        msg = {"jsonrpc": "2.0", "id": my_id, "method": method, "params": params}
        if on_progress is not None:
            msg["params"] = dict(params, _meta={"progressToken": my_id})
        self._send(msg)
        while True:
            try:
                reply = self._lines.get(timeout=timeout)
            except queue.Empty as exc:
                raise ConcatError(f"Concat didn't answer within {int(timeout)} s.") from exc
            if reply is None:
                raise ConcatError("Concat stopped unexpectedly.")
            if reply.get("method") == "notifications/progress" and on_progress:
                on_progress(reply.get("params") or {})
                continue
            if reply.get("id") != my_id:
                continue
            if "error" in reply:
                err = reply["error"]
                raise ConcatError(_friendly(str(err.get("message", err)),
                                            (err.get("data") or {}).get("code")))
            return reply.get("result") or {}

    def _check_tools(self, tools: list[dict]) -> None:
        have = {t["name"]: set((t.get("inputSchema") or {}).get("properties", {})) for t in tools}
        missing = []
        for name, args in TOOLS_USED.items():
            if name not in have:
                missing.append(name)
            elif args - have[name]:
                missing.append(f"{name}({', '.join(sorted(args - have[name]))})")
        if missing:
            raise ConcatError("This Concat version isn't supported yet (it lacks "
                              f"{', '.join(missing)}). Tell Plamen.")

    def call(self, tool: str, timeout: float = CALL_TIMEOUT_S,
             on_progress: Callable[[dict], None] | None = None, **args) -> dict:
        """Calls a tool; returns its structured result. Raises ConcatError
        with Concat's own message on a refusal."""
        args = {k: v for k, v in args.items() if v is not None}
        result = self._request("tools/call", {"name": tool, "arguments": args},
                               timeout=timeout, on_progress=on_progress)
        if result.get("isError"):
            text = " ".join(c.get("text", "") for c in result.get("content", []))
            code = None
            try:
                code = json.loads(text).get("code")
                text = json.loads(text).get("message", text)
            except (ValueError, AttributeError):
                pass
            raise ConcatError(_friendly(text.strip() or f"Concat refused {tool}.", code))
        if tool == "project_open":
            self._opened.add(args["path"])
        elif tool == "project_create":
            self._opened.add(str(Path(args["location"]) / args["name"]))
        if tool == "project_close":
            self._opened.discard(args.get("path"))
        structured = result.get("structuredContent")
        if structured is not None:
            return structured
        text = " ".join(c.get("text", "") for c in result.get("content", [])
                        if c.get("type") == "text")
        try:
            return json.loads(text)
        except ValueError:
            return {"text": text}

    def opened(self, path: str) -> None:
        """Remember a project folder to close on exit."""
        self._opened.add(path)


def status(configured: str | None = None, roots: list[Path] | None = None) -> dict:
    """For Setup check: {"found": bool, "path", "version", "warning"}."""
    exe = find_concat(configured)
    if exe is None:
        return {"found": False}
    out = {"found": True, "path": str(exe), "version": None, "warning": None}
    try:
        with ConcatSession(roots or [Path.home()], exe=exe) as c:
            out["version"] = c.version
    except ConcatError as exc:
        out["warning"] = str(exc)
        return out
    if out["version"] and _newer(out["version"], TESTED_CONCAT_VERSION):
        out["warning"] = (f"Concat {out['version']} is newer than the version Studio Helper "
                          f"was tested with ({TESTED_CONCAT_VERSION}). If video steps fail, "
                          "tell Plamen.")
    return out


def _newer(a: str, b: str) -> bool:
    def parts(v):
        return tuple(int(p) for p in v.split(".") if p.isdigit())
    return parts(a) > parts(b)
