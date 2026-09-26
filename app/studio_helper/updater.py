"""Explicit, user-initiated self-update against GitHub Releases
(SPEC.md §8/§15 decisions, 2026-09-24).

This is the ONE place in the whole app allowed to make a non-loopback
network call. It never runs automatically -- not on startup, not on a
timer, not from `--selftest` -- only when the user clicks "Check for
updates" / "Download & install" in the UI. No client data is ever
sent; the only traffic is a GET against GitHub's public release API
and CDN, same as opening the releases page in a browser would do.

Downloads are verified against the release's own SHA256SUMS asset
before anything is extracted or installed, the same hash-pinning
discipline packaging/build_release.ps1 already applies to the
embeddable Python download (SPEC.md §8 supply chain).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from studio_helper import __version__, paths

REPO = "plpetkov-tech/studio-helper"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
USER_AGENT = f"StudioHelper/{__version__} (+https://github.com/{REPO})"
CHECK_TIMEOUT_SECONDS = 15
DOWNLOAD_TIMEOUT_SECONDS = 120


class UpdateError(Exception):
    """Anything that should reach the UI as a plain message, never a
    stack trace (SPEC.md §2.5, §7)."""


@dataclass
class UpdateInfo:
    current_version: str
    latest_version: str
    available: bool
    notes: str
    html_url: str
    zip_url: str | None
    zip_name: str | None
    sha256sums_url: str | None

    def to_dict(self) -> dict:
        return {
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "available": self.available,
            "notes": self.notes,
            "html_url": self.html_url,
        }


def _parse_version(tag: str) -> tuple[int, ...]:
    """"v0.3.0" -> (0, 3, 0). Unrecognised chunks become 0 rather than
    raising -- a malformed tag should show as "not newer", not crash
    the update check."""
    tag = tag.strip().lstrip("vV")
    parts: list[int] = []
    for chunk in tag.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_newer(current: str, latest: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def _get_json(url: str, timeout: float) -> dict:
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise UpdateError(f"Could not reach GitHub: {exc}") from exc


def _get_bytes(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - github asset URL
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise UpdateError(f"Download failed: {exc}") from exc


def check_for_update() -> UpdateInfo:
    data = _get_json(API_URL, CHECK_TIMEOUT_SECONDS)
    tag = data.get("tag_name", "")
    assets = data.get("assets") or []
    zip_asset = next((a for a in assets if a.get("name", "").endswith(".zip")), None)
    sums_asset = next((a for a in assets if a.get("name", "") == "SHA256SUMS"), None)

    return UpdateInfo(
        current_version=__version__,
        latest_version=(tag.lstrip("vV") or tag) if tag else __version__,
        available=bool(tag) and is_newer(__version__, tag),
        notes=(data.get("body") or "").strip(),
        html_url=data.get("html_url") or f"https://github.com/{REPO}/releases",
        zip_url=zip_asset.get("browser_download_url") if zip_asset else None,
        zip_name=zip_asset.get("name") if zip_asset else None,
        sha256sums_url=sums_asset.get("browser_download_url") if sums_asset else None,
    )


def _expected_sha256(sums_text: str, filename: str) -> str | None:
    for line in sums_text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0].lower()
    return None


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    """Rejects any entry that would land outside `dest` (zip-slip;
    SPEC.md §8 path safety), same guard the file-poller's zip
    auto-extraction already applies."""
    dest_resolved = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if target != dest_resolved and dest_resolved not in target.parents:
            raise UpdateError(f"Refusing to extract unsafe path in update zip: {member.filename}")
    zf.extractall(dest)


def download_and_stage(info: UpdateInfo) -> Path:
    """Downloads the release zip, verifies its SHA256 against the
    release's own SHA256SUMS asset, and extracts it into a sibling
    `StudioHelper-v<new>` folder next to the currently running
    install. Never touches the currently running install's files.
    Returns the new version's folder."""
    if not info.zip_url or not info.zip_name or not info.sha256sums_url:
        raise UpdateError("That release is missing its zip or SHA256SUMS file.")

    install_root = paths.bundled_root().parent

    zip_bytes = _get_bytes(info.zip_url, DOWNLOAD_TIMEOUT_SECONDS)
    sums_text = _get_bytes(info.sha256sums_url, CHECK_TIMEOUT_SECONDS).decode(
        "utf-8", errors="replace"
    )
    expected = _expected_sha256(sums_text, info.zip_name)
    if expected is None:
        raise UpdateError("Could not find this file's hash in SHA256SUMS -- refusing to install.")
    actual = hashlib.sha256(zip_bytes).hexdigest()
    if actual != expected:
        raise UpdateError(
            f"Downloaded file's checksum doesn't match the release "
            f"(expected {expected}, got {actual}) -- refusing to install."
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="studiohelper-update-"))
    staging = install_root / f".studiohelper-update-staging-{uuid.uuid4().hex[:8]}"
    try:
        tmp_zip = tmp_dir / info.zip_name
        tmp_zip.write_bytes(zip_bytes)

        staging.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_zip) as zf:
            _safe_extract(zf, staging)

        entries = [p for p in staging.iterdir() if p.is_dir()]
        if len(entries) != 1:
            raise UpdateError("Unexpected release zip layout -- refusing to install.")

        final_dir = install_root / f"StudioHelper-v{info.latest_version}"
        if final_dir.exists():
            shutil.rmtree(final_dir)
        entries[0].rename(final_dir)
        return final_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)


# PowerShell rather than .bat: needs Wait-Process (waits on the old
# app's PID, not a fixed sleep) and reliable quoted-path handling for
# folder names containing spaces ("Start Studio Helper.bat" itself).
# Invoked with -ExecutionPolicy Bypass so it runs regardless of the
# machine's persistent script-execution policy, without changing that
# policy (SPEC.md §2.2: user-level only, no lasting system changes).
#
# The old install is renamed to "<OldDir>.previous", never deleted
# outright, so a release that fails to start still leaves a working
# copy right next to it to fall back to by hand (SPEC.md §15,
# 2026-09-24) -- there is no automated health check of the new
# version here, so this is the safety net for when one would have
# caught something. At most one rollback copy is kept: a
# ".previous" left over from the update before last is removed
# first, right before this update's old install takes its place.
_INSTALL_DIR_RE = re.compile(r"^StudioHelper-v(\d+(?:\.\d+)*)(\.previous)?$")
_LAUNCHER = "Start Studio Helper.bat"


def cleanup_old_installs(current_root: Path) -> list[Path]:
    """Deletes install folders left next to this one by earlier updates.
    The relaunch script only ever removes `<old>.previous` under the
    old version's own name, so every update used to leave one more
    `StudioHelper-vX.previous` behind. Keeps this install and the
    newest older one as the rollback copy; never touches a newer
    version (a manual rollback) or anything without our launcher in
    it. Returns the folders deleted."""
    current = _INSTALL_DIR_RE.match(current_root.name)
    if not current:
        return []  # dev checkout or unusual layout: nothing to judge by
    current_version = _parse_version(current.group(1))

    older = []
    for sibling in current_root.parent.iterdir():
        m = _INSTALL_DIR_RE.match(sibling.name)
        if (
            m and sibling != current_root and sibling.is_dir()
            and (sibling / _LAUNCHER).exists()
            and _parse_version(m.group(1)) < current_version
        ):
            older.append((_parse_version(m.group(1)), sibling))
    older.sort(key=lambda item: item[0])

    removed = []
    for _version, folder in older[:-1]:  # the newest older one stays as rollback
        shutil.rmtree(folder, ignore_errors=True)
        if not folder.exists():
            removed.append(folder)
    return removed


_RELAUNCH_PS1 = """
param(
    [Parameter(Mandatory=$true)][int]$OldPid,
    [Parameter(Mandatory=$true)][string]$OldDir,
    [Parameter(Mandatory=$true)][string]$NewDir
)
try { Wait-Process -Id $OldPid -Timeout 30 -ErrorAction SilentlyContinue } catch {}
Start-Sleep -Seconds 1

$previousDir = "$OldDir.previous"
if (Test-Path -LiteralPath $previousDir) {
    Remove-Item -LiteralPath $previousDir -Recurse -Force -ErrorAction SilentlyContinue
}
if (Test-Path -LiteralPath $OldDir) {
    $previousName = Split-Path -Leaf $previousDir
    Rename-Item -LiteralPath $OldDir -NewName $previousName -ErrorAction SilentlyContinue
}

Start-Process -FilePath (Join-Path $NewDir "Start Studio Helper.bat") -WorkingDirectory $NewDir
Start-Sleep -Seconds 2
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""


def schedule_relaunch(new_dir: Path) -> None:
    """Writes a small PowerShell helper to %TEMP% and launches it
    detached. It waits for THIS process to actually exit before
    deleting the old install folder (so nothing locked is touched
    while still in use), then starts the new version and deletes
    itself. The caller is responsible for shutting this process down
    right after calling this (e.g. via the existing /api/quit)."""
    if sys.platform != "win32":
        raise UpdateError("Auto-update is only supported on Windows.")

    old_dir = paths.bundled_root()
    script_path = Path(tempfile.gettempdir()) / f"studiohelper-relaunch-{uuid.uuid4().hex[:8]}.ps1"
    script_path.write_text(_RELAUNCH_PS1, encoding="utf-8")

    # CREATE_NO_WINDOW alone: it and DETACHED_PROCESS are documented by
    # Microsoft as mutually exclusive (both control console allocation),
    # and this flag alone is enough to keep the helper's console hidden.
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-OldPid",
            str(os.getpid()),
            "-OldDir",
            str(old_dir),
            "-NewDir",
            str(new_dir),
        ],
        creationflags=creationflags,
        close_fds=True,
    )
