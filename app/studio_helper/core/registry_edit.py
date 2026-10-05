"""Edit or delete one format in her registry.yaml from the Formats page.

Like custom_formats.save_format, this edits the file as text so her
comments, layout and every other format survive untouched: only the
lines of the changed fields are replaced. The whole file is re-validated
afterwards and restored if it doesn't load.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from studio_helper.core.registry import Registry, RegistryError, load_registry

# What the form can change. Required ones can't be emptied.
EDITABLE = ("name", "group", "notes", "size", "bleed_mm", "safe_mm", "exports", "tiff_ppi")
REQUIRED = ("name", "size", "exports")


class FormatEditError(ValueError):
    pass


def _render(value) -> str:
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {v}" for k, v in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    dumped = yaml.safe_dump(value, allow_unicode=True, width=10_000).strip()
    return dumped.removesuffix("\n...").removesuffix("...").strip()


def _entry_span(lines: list[str], fid: str) -> tuple[int, int]:
    """[start, end) line range of format `fid`: its `  - id:` line and
    every deeper-indented line after it."""
    head_re = re.compile(rf"^  - id: {re.escape(fid)}\s*(#.*)?$")
    head = next((i for i, ln in enumerate(lines) if head_re.match(ln.rstrip("\n"))), None)
    if head is None:
        raise FormatEditError(f"No format '{fid}' in the formats file.")
    end = head + 1
    while end < len(lines) and (lines[end].startswith("    ") or not lines[end].strip()):
        end += 1
    while end > head + 1 and not lines[end - 1].strip():  # trailing blank lines aren't ours
        end -= 1
    return head, end


def _field_span(lines: list[str], start: int, end: int, key: str) -> tuple[int, int] | None:
    """Lines holding `    key: ...`, including a block value on the
    lines below it (anything indented deeper than the key)."""
    key_re = re.compile(rf"^    {re.escape(key)}\s*:")
    for i in range(start + 1, end):
        if key_re.match(lines[i]):
            j = i + 1
            while j < end and (lines[j].startswith("     ") or lines[j].startswith("    -")):
                j += 1
            return i, j
    return None


def _write_checked(path: Path, original: str, lines: list[str]) -> Registry:
    path.write_text("".join(lines), encoding="utf-8")
    try:
        return load_registry(path)
    except RegistryError:
        path.write_text(original, encoding="utf-8")
        raise


def update_format(path: Path, fid: str, changes: dict) -> Registry:
    """Applies `changes` ({field: value}; None or "" removes an optional
    field) to format `fid`."""
    unknown = set(changes) - set(EDITABLE)
    if unknown:
        raise FormatEditError(f"Can't edit {', '.join(sorted(unknown))} here.")
    for key in REQUIRED:
        if key in changes and changes[key] in (None, "", [], {}):
            raise FormatEditError(f"The {key} can't be empty.")

    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    start, end = _entry_span(lines, fid)

    for key in EDITABLE:  # fixed order, so inserted lines land predictably
        if key not in changes:
            continue
        value = changes[key]
        span = _field_span(lines, start, end, key)
        new = [] if value in (None, "") else [f"    {key}: {_render(value)}\n"]
        if span:
            lines[span[0]:span[1]] = new
            end += len(new) - (span[1] - span[0])
        elif new:
            lines[end:end] = new
            end += 1
    return _write_checked(path, original, lines)


def delete_format(path: Path, fid: str) -> Registry:
    """Removes format `fid` (and the comment lines directly above it)."""
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    start, end = _entry_span(lines, fid)
    while start > 0 and lines[start - 1].startswith("  #"):
        start -= 1
    if end < len(lines) and not lines[end].strip():
        end += 1  # and one blank separator line
    del lines[start:end]
    return _write_checked(path, original, lines)
