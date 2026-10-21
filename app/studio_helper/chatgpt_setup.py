"""Adds Studio Helper to ChatGPT desktop's MCP servers by itself.

The ChatGPT desktop app keeps its local MCP servers in Codex's
config.toml (`%USERPROFILE%\\.codex\\config.toml`, or `%CODEX_HOME%`),
one `[mcp_servers.<name>]` table each. On every start, while Settings ->
ChatGPT is on, the app writes its own table there, pointing at this
install's console python.exe, so an update keeps ChatGPT working with
nothing to paste (Plamen, 2026-10-21). The skill goes next to it, in
`skills/studio-helper/SKILL.md`.

Her file is edited as text: only our table (and the comment line above
it) is replaced, everything else stays byte for byte, and nothing is
written unless the result still parses. Like the desktop shortcut
(launcher.py), a table she deleted isn't added back on the next start;
Settings -> "Add to ChatGPT" adds it again.
"""

from __future__ import annotations

import logging
import os
import re
import tomllib
from pathlib import Path

logger = logging.getLogger(__name__)

SERVER = "studio-helper"
HEADER = f"[mcp_servers.{SERVER}]"
COMMENT = "# Added by Studio Helper (Settings > ChatGPT turns it off). It rewrites this table."
_OUR_HEADER = re.compile(r"^\s*\[\s*mcp_servers\s*\.\s*(\"studio-helper\"|studio-helper)\s*[\].]")
_ANY_HEADER = re.compile(r"^\s*\[")
SKILL_DIR = Path("skills") / SERVER


def codex_home() -> Path:
    env = os.environ.get("CODEX_HOME")
    return Path(env) if env else Path.home() / ".codex"


def config_file() -> Path:
    return codex_home() / "config.toml"


def _toml_str(value: str) -> str:
    # a literal string needs no escaping of Windows backslashes
    if "'" not in value and "\n" not in value:
        return f"'{value}'"
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def server_block(python_exe: Path, install_root: Path, nl: str = "\n") -> str:
    lines = [
        COMMENT,
        HEADER,
        f"command = {_toml_str(str(python_exe))}",
        "args = ['-m', 'studio_helper', '--mcp']",
        f"cwd = {_toml_str(str(install_root))}",
        # the app may have to start first; making videos takes minutes
        "startup_timeout_sec = 30",
        "tool_timeout_sec = 900",
    ]
    return nl.join(lines) + nl


def _blank_or_comment(line: str) -> bool:
    return not line.strip() or line.lstrip().startswith("#")


def _split(text: str) -> tuple[list[str], list[str], list[str]]:
    """(before, ours, after) as lines with their endings."""
    lines = text.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if _OUR_HEADER.match(ln)), None)
    if start is None:
        return lines, [], []
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if _ANY_HEADER.match(ln) and not _OUR_HEADER.match(ln):
            break
        end += 1
    # trailing blank lines and the next table's own comments stay with it
    while end - 1 > start and _blank_or_comment(lines[end - 1]):
        end -= 1
    if start > 0 and lines[start - 1].strip() == COMMENT:
        start -= 1
    return lines[:start], lines[start:end], lines[end:]


def has_server(text: str) -> bool:
    return bool(_split(text)[1])


def with_server(text: str, block: str) -> str:
    before, ours, after = _split(text)
    if ours:
        return "".join(before) + block + "".join(after)
    nl = "\r\n" if "\r\n" in text else "\n"
    lead = text
    if lead and not lead.endswith(("\n", "\r\n")):
        lead += nl
    if lead.strip():
        lead += nl
    return lead + block


def without_server(text: str) -> str:
    before, ours, after = _split(text)
    if not ours:
        return text
    out = "".join(before)
    rest = "".join(after)
    if out.endswith(("\n\n", "\r\n\r\n")) and not rest.strip():
        out = out.rstrip("\r\n") + ("\r\n" if "\r\n" in text else "\n")
    return out + rest


def _parses(text: str) -> bool:
    try:
        tomllib.loads(text)
        return True
    except tomllib.TOMLDecodeError:
        return False


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".studio-helper-tmp")
    tmp.write_bytes(text.encode("utf-8"))
    os.replace(tmp, path)


def _pasted_by_hand(text: str) -> bool:
    """She (or an older guide) pasted our launcher under another name."""
    before, _ours, after = _split(text)
    return "studio-helper-mcp.cmd" in "".join(before + after)


def ensure(install_root: Path, cfg, force: bool = False, skill: Path | None = None) -> str:
    """Keeps ChatGPT's entry for Studio Helper pointing at this install.
    Returns "added", "updated", "unchanged", "removed-by-user",
    "pasted-by-hand", "no-chatgpt", "off", "unreadable" or "skipped"."""
    python = install_root / "runtime" / "python.exe"
    if not python.exists():
        return "skipped"  # a dev checkout, not a release
    path = config_file()
    if not getattr(cfg, "assistants_enabled", True):
        if remove() and getattr(cfg, "chatgpt_mcp_added", False):
            cfg.chatgpt_mcp_added = False  # we took it out: turning it on adds it back
            cfg.save()
        return "off"
    if not path.parent.is_dir() and not force:
        return "no-chatgpt"  # never seen ChatGPT/Codex settings on this PC
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except FileNotFoundError:
        raw, text = b"", ""
    except (OSError, UnicodeDecodeError):
        return "unreadable"
    if text and not _parses(text):
        return "unreadable"  # never touch a file we can't read back
    nl = "\r\n" if "\r\n" in text else ("\n" if text else os.linesep)
    present = has_server(text)
    if not present:
        if _pasted_by_hand(text) and not force:
            return "pasted-by-hand"
        if getattr(cfg, "chatgpt_mcp_added", False) and not force:
            return "removed-by-user"
    new = with_server(text, server_block(python, install_root, nl))
    if not _parses(new):
        logger.warning("ChatGPT config would not parse with our table; left alone")
        return "unreadable"
    _install_skill(skill)
    if new == text:
        result = "unchanged"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        if raw and not path.with_name("config.toml.before-studio-helper").exists():
            path.with_name("config.toml.before-studio-helper").write_bytes(raw)
        _write(path, new)
        result = "updated" if present else "added"
    if not getattr(cfg, "chatgpt_mcp_added", False):
        cfg.chatgpt_mcp_added = True
        cfg.save()
    return result


def remove() -> bool:
    """Takes our table (and skill) out of ChatGPT's settings."""
    path = config_file()
    try:
        text = path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    new = without_server(text)
    if new == text or not _parses(new):
        return False
    _write(path, new)
    skill = codex_home() / SKILL_DIR / "SKILL.md"
    if skill.is_file() and _is_our_skill(skill.read_text(encoding="utf-8", errors="replace")):
        skill.unlink()
    return True


def status() -> str:
    """For Settings: "added", "missing" or "no-chatgpt"."""
    path = config_file()
    if not path.parent.is_dir():
        return "no-chatgpt"
    try:
        return "added" if has_server(path.read_text(encoding="utf-8")) else "missing"
    except (OSError, UnicodeDecodeError):
        return "missing"


def _is_our_skill(text: str) -> bool:
    return bool(re.search(r"^name:\s*studio-helper\s*$", text, re.MULTILINE))


def _install_skill(skill: Path | None) -> None:
    skill = skill or Path(__file__).parent / "assistant" / "SKILL.md"
    if not skill.is_file():
        return
    dest = codex_home() / SKILL_DIR / "SKILL.md"
    data = skill.read_bytes()
    try:
        if dest.exists():
            current = dest.read_bytes()
            if current == data or not _is_our_skill(current.decode("utf-8", "replace")):
                return  # up to date, or a file of hers with our folder name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError:
        logger.exception("Could not write the ChatGPT skill")
