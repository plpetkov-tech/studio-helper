"""COM bridge to Adobe apps via comtypes (SPEC.md §6.3).

Windows-only. On any other platform, or if comtypes/the app itself
isn't available, every function here raises AdobeBridgeError cleanly
-- the UI is expected to catch that and show the manual "File >
Scripts" fallback path, never a stack trace (SPEC.md §2.5, §6.3).
"""

from __future__ import annotations

import json
import logging
import sys
import threading
from pathlib import Path

logger = logging.getLogger("studio_helper.adobe")

LAUNCH_TIMEOUT_SECONDS = 120

_com_state = threading.local()


class AdobeBridgeError(Exception):
    """COM connection or invocation failed; caller shows the manual
    File > Scripts fallback (SPEC.md §6.3)."""


def _comtypes_client():
    if sys.platform != "win32":
        raise AdobeBridgeError("Adobe app automation is only available on Windows.")
    try:
        import comtypes.client
    except ImportError as exc:
        raise AdobeBridgeError(f"comtypes is not available: {exc}") from exc
    return comtypes.client


def _ensure_com_initialized() -> None:
    """COM apartments are per-thread: every thread that makes a COM
    call needs its own CoInitialize. Found on a real machine, not in
    testing here -- every Illustrator/Photoshop action failed with
    "CoInitialize has not been called" (WinError -2147221008),
    because AppContext.tasks (SPEC.md §6.2) runs each action on a
    fresh background thread that had never called it."""
    if getattr(_com_state, "initialized", False):
        return
    import comtypes

    comtypes.CoInitialize()
    _com_state.initialized = True


def is_running(progid: str) -> bool:
    """Passive check: is the app already running and controllable?
    Never launches it -- used by the Setup check page, which
    shouldn't have the side effect of starting Illustrator just
    because she opened a settings screen."""
    if sys.platform != "win32":
        return False
    try:
        client = _comtypes_client()
        _ensure_com_initialized()
    except AdobeBridgeError:
        return False
    try:
        client.GetActiveObject(progid)
        return True
    except OSError:
        return False


def connect(progid: str):
    """Connects to a running instance, or launches one. Runs entirely
    on the calling thread: COM objects are bound to the apartment
    that created them, so creating one on a helper thread (as an
    earlier version of this did, to enforce a timeout) and calling it
    from another breaks -- at best a marshaling error, at worst the
    same CoInitialize error this fixes. The caller already runs
    inside a background Task (SPEC.md §6.2), so a slow Illustrator
    launch still never blocks the UI; it just makes that one task take
    longer, which is what the polling UI already expects."""
    client = _comtypes_client()
    _ensure_com_initialized()

    try:
        return client.GetActiveObject(progid)
    except OSError:
        pass  # not running yet -- launch it below

    try:
        return client.CreateObject(progid, dynamic=True)
    except Exception as exc:  # noqa: BLE001 - reported to the caller, not raised as-is
        raise AdobeBridgeError(f"Could not start {progid}: {exc}") from exc


def run_jsx(app, jsx_path: Path, args: dict) -> dict:
    """Invokes a JSX file via DoJavaScript, per the protocol in
    SPEC.md §6.3: arguments go through json.dumps only (never string
    concatenation of user input), and the script's last expression is
    JSON.stringify(result)."""
    forward_slash_path = str(jsx_path).replace("\\", "/")
    code = f"var SH_ARGS = {json.dumps(args)}; $.evalFile({json.dumps(forward_slash_path)});"

    try:
        raw = app.DoJavaScript(code)
    except Exception as exc:  # noqa: BLE001 - COM errors surface as generic exceptions
        raise AdobeBridgeError(f"Illustrator reported an error: {exc}") from exc

    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise AdobeBridgeError(f"Illustrator returned an unexpected result: {raw!r}") from exc
