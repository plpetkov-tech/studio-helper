"""Best-effort "open this in the OS" helpers, shared across handlers.
Never raise -- there's nothing useful the UI can do if the OS call
itself fails (SPEC.md §7)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

OPEN_TIMEOUT_SECONDS = 5


def open_path(path: Path, *, reveal: bool) -> None:
    """`reveal=True` opens the containing app (Explorer/Finder/file
    manager) on a folder; `reveal=False` opens a file in the default
    text editor. A hung or misbehaving OS opener must never freeze the
    request thread indefinitely -- caught for real in testing, where
    xdg-open hung in a headless sandbox."""
    try:
        if sys.platform == "win32":
            cmd = "explorer.exe" if reveal else "notepad.exe"
            subprocess.run([cmd, str(path)], check=False, timeout=OPEN_TIMEOUT_SECONDS)
        elif sys.platform == "darwin":
            subprocess.run(
                ["open"] + ([] if reveal else ["-t"]) + [str(path)],
                check=False,
                timeout=OPEN_TIMEOUT_SECONDS,
            )
        else:
            subprocess.run(["xdg-open", str(path)], check=False, timeout=OPEN_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        pass
