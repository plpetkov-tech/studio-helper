"""A desktop shortcut and a fixed launcher folder that survive updates.

Every update installs into a new `StudioHelper-vX.Y.Z` folder and renames
the old one, so anything pointing into the install folder breaks. Like
the Figma plugin folder (paths.figma_plugin_dir), these are refreshed
from the running install on every start:

- <app data>/launcher/Studio Helper.cmd       starts the app
- <app data>/launcher/studio-helper-mcp.cmd   the assistant (MCP) command
- Desktop/Studio Helper.lnk                   created once; refreshed only
                                              while it exists, so a
                                              shortcut she deleted stays
                                              deleted (ROADMAP R13)
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Protocol

from studio_helper import paths

logger = logging.getLogger(__name__)

SHORTCUT_NAME = "Studio Helper.lnk"
START_CMD = "Studio Helper.cmd"
MCP_CMD = "studio-helper-mcp.cmd"

# Only a shortcut aimed at a Studio Helper install's pythonw.exe is ours.
_OUR_TARGET = re.compile(r"[\\/]StudioHelper[^\\/]*[\\/]runtime[\\/]pythonw\.exe$", re.IGNORECASE)


def launcher_dir() -> Path:
    return paths.app_data_dir() / "launcher"


def launcher_files(install_root: Path) -> dict[str, str]:
    """{file name: contents} for the fixed launcher folder."""
    runtime = install_root / "runtime"
    return {
        START_CMD: (
            "@echo off\r\n"
            f'start "" "{runtime / "pythonw.exe"}" -m studio_helper\r\n'
        ),
        # console python.exe: the MCP transport is stdin/stdout
        MCP_CMD: (
            "@echo off\r\n"
            f'"{runtime / "python.exe"}" -m studio_helper --mcp %*\r\n'
        ),
    }


def write_launchers(install_root: Path) -> list[str]:
    """Rewrites the launcher files whose contents differ. Returns the
    names written."""
    folder = launcher_dir()
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, text in launcher_files(install_root).items():
        path = folder / name
        data = text.encode("utf-8")
        try:
            if path.read_bytes() == data:
                continue
        except OSError:
            pass
        path.write_bytes(data)
        written.append(name)
    # the assistant skill (R12), next to the command ChatGPT runs
    skill = Path(__file__).parent / "assistant" / "SKILL.md"
    if skill.is_file():
        dest = folder / "studio-helper-SKILL.md"
        data = skill.read_bytes()
        if not dest.exists() or dest.read_bytes() != data:
            dest.write_bytes(data)
            written.append(dest.name)
    return written


class ShortcutIO(Protocol):
    def desktop(self) -> Path | None: ...
    def read_target(self, lnk: Path) -> str | None: ...
    def write(
        self, lnk: Path, target: Path, args: str, workdir: Path, icon: Path | None
    ) -> None: ...


def is_ours(target: str | None) -> bool:
    return bool(target) and bool(_OUR_TARGET.search(target))


def ensure_desktop_shortcut(install_root: Path, cfg, io: ShortcutIO | None = None) -> str:
    """Creates the desktop shortcut the first time, then keeps it
    pointing at the running install. Returns what happened:
    "created", "updated", "unchanged", "deleted-by-user", "foreign",
    or "skipped"."""
    target = install_root / "runtime" / "pythonw.exe"
    if not target.exists():
        return "skipped"  # running from a dev checkout, not a release
    io = io or _windows_io()
    if io is None:
        return "skipped"
    desktop = io.desktop()
    if desktop is None or not desktop.is_dir():
        return "skipped"
    lnk = desktop / SHORTCUT_NAME
    icon = install_root / "app" / "studio_helper" / "web" / "static" / "app.ico"
    icon = icon if icon.exists() else None

    if lnk.exists():
        current = io.read_target(lnk)
        if not is_ours(current):
            return "foreign"  # a file of hers with the same name: never touch it
        if current and Path(current) == target:
            return "unchanged"
        io.write(lnk, target, "-m studio_helper", install_root, icon)
        return "updated"
    if getattr(cfg, "desktop_shortcut_created", False):
        return "deleted-by-user"
    io.write(lnk, target, "-m studio_helper", install_root, icon)
    cfg.desktop_shortcut_created = True
    cfg.save()
    return "created"


def remove_desktop_shortcut(io: ShortcutIO | None = None) -> bool:
    io = io or _windows_io()
    desktop = io.desktop() if io else None
    if desktop is None:
        return False
    lnk = desktop / SHORTCUT_NAME
    if lnk.exists() and is_ours(io.read_target(lnk)):
        lnk.unlink()
        return True
    return False


class _WindowsShortcuts:
    """WScript.Shell through comtypes (already a runtime dependency),
    so no PowerShell window flashes up."""

    def _shell(self):
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        return comtypes.client.CreateObject("WScript.Shell", dynamic=True)

    def desktop(self) -> Path | None:
        # The real Desktop: corporate PCs often redirect it into OneDrive,
        # so %USERPROFILE%\Desktop can be the wrong folder.
        import ctypes
        from ctypes import wintypes

        # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}, in GUID byte order
        folderid_desktop = ctypes.c_char_p(bytes.fromhex("3ACCBFB42CDB4C42B0297FE99A87C641"))
        out = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        shell32.SHGetKnownFolderPath.argtypes = [
            ctypes.c_char_p, wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
        if shell32.SHGetKnownFolderPath(folderid_desktop, 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return Path(out.value)
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)

    def read_target(self, lnk: Path) -> str | None:
        try:
            return str(self._shell().CreateShortcut(str(lnk)).TargetPath) or None
        except Exception:  # noqa: BLE001 - unreadable shortcut: treat as not ours
            return None

    def write(self, lnk, target, args, workdir, icon) -> None:
        sc = self._shell().CreateShortcut(str(lnk))
        sc.TargetPath = str(target)
        sc.Arguments = args
        sc.WorkingDirectory = str(workdir)
        sc.Description = "Studio Helper"
        if icon is not None:
            sc.IconLocation = f"{icon},0"
        sc.Save()


def _windows_io() -> ShortcutIO | None:
    return _WindowsShortcuts() if sys.platform == "win32" else None
