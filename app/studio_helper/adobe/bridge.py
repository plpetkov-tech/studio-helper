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


def is_running(progid: str) -> bool:
    """Passive check: is the app already running and controllable?
    Never launches it -- used by the Setup check page, which
    shouldn't have the side effect of starting Illustrator just
    because she opened a settings screen."""
    if sys.platform != "win32":
        return False
    try:
        client = _comtypes_client()
    except AdobeBridgeError:
        return False
    try:
        client.GetActiveObject(progid)
        return True
    except OSError:
        return False


def connect(progid: str, timeout: float = LAUNCH_TIMEOUT_SECONDS):
    """Connects to a running instance, or launches one. May block for
    up to `timeout` seconds if the app needs to cold-start."""
    client = _comtypes_client()

    try:
        return client.GetActiveObject(progid)
    except OSError:
        pass  # not running yet -- launch it below

    launch_result: dict = {}

    def _launch() -> None:
        try:
            launch_result["app"] = client.CreateObject(progid, dynamic=True)
        except Exception as exc:  # noqa: BLE001 - reported to the caller, not raised here
            launch_result["error"] = exc

    thread = threading.Thread(target=_launch, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        raise AdobeBridgeError(f"{progid} did not start within {timeout:.0f}s.")
    if "error" in launch_result:
        raise AdobeBridgeError(f"Could not start {progid}: {launch_result['error']}")
    return launch_result["app"]


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
