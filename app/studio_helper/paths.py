"""Filesystem locations Studio Helper is allowed to touch (SPEC.md §2.2).

On Windows (the shipped target) these resolve under %APPDATA%,
%LOCALAPPDATA% and %USERPROFILE%\\Documents. On other platforms (used
only for running the test suite in CI, per SPEC.md §9) they fall back
to XDG-ish locations under the user's home directory so the core
modules stay importable and testable without a Windows box.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "StudioHelper"


def _windows_appdata() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata)
    return Path.home() / "AppData" / "Roaming"


def app_data_dir() -> Path:
    """Per-user, writable, survives app updates. SPEC.md §5.2."""
    if sys.platform == "win32":
        base = _windows_appdata()
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / APP_NAME


def logs_dir() -> Path:
    return app_data_dir() / "logs"


def default_jobs_root() -> Path:
    """SPEC.md §5.2: default jobs_root is %USERPROFILE%\\Documents\\Studio Jobs."""
    if sys.platform == "win32":
        docs = Path(os.environ.get("USERPROFILE", Path.home())) / "Documents"
    else:
        docs = Path.home() / "Documents"
    return docs / "Studio Jobs"


def config_path() -> Path:
    return app_data_dir() / "config.json"


def user_registry_path() -> Path:
    return app_data_dir() / "registry.yaml"


def instance_path() -> Path:
    return app_data_dir() / "instance.json"


def bundled_root() -> Path:
    """Root of the release layout (or repo root in dev): the directory
    that contains both `app/` and `defaults/` (SPEC.md §5.1)."""
    return Path(__file__).resolve().parents[2]


def bundled_registry_path() -> Path:
    return bundled_root() / "defaults" / "registry.yaml"


def ensure_app_data_dirs() -> None:
    app_data_dir().mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)


def is_inside(path: Path, allowed_root: Path) -> bool:
    """True if `path` resolves inside `allowed_root`. Used to reject
    `..`/absolute-path escapes from the UI (SPEC.md §8 path safety)."""
    try:
        path.resolve().relative_to(allowed_root.resolve())
        return True
    except ValueError:
        return False
