"""Formats typed into the app instead of registry.yaml: a one-off size
the print shop just sent ("Custom size" on New job), optionally saved
to the registry so it can be picked next time.

Saving edits her registry.yaml as text -- the new entry is inserted at
the end of the `formats:` list -- so her comments and layout survive,
which a load-and-dump round trip through PyYAML would destroy.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from studio_helper.core import naming
from studio_helper.core.registry import (
    Registry,
    RegistryError,
    load_registry,
    resolve_format,
    validate_format,
)

KINDS = {
    # kind: (unit, allowed exports)
    "print": ("mm", ("tiff", "pdf")),
    "screen": ("px", ("png", "jpg")),
    "social": ("px", ("png", "jpg")),
}


class CustomFormatError(ValueError):
    pass


def _number(spec: dict, key: str, *, required: bool, minimum: float = 0) -> float | None:
    value = spec.get(key)
    if value in (None, ""):
        if required:
            raise CustomFormatError(f"Enter the {key.replace('_', ' ')}.")
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise CustomFormatError(f"The {key.replace('_', ' ')} must be a number.") from exc
    if number < minimum or (required and number <= 0):
        raise CustomFormatError(f"The {key.replace('_', ' ')} must be more than {minimum:g}.")
    return int(number) if number == int(number) else number


def build_format(spec: dict, taken_ids: set[str]) -> dict:
    """A registry-shaped format entry (not yet resolved) from the
    New job / Formats form. `spec` keys: name, kind, w, h, export, and
    optionally bleed_mm, safe_mm, group, notes."""
    name = str(spec.get("name") or "").strip()
    if not name:
        raise CustomFormatError("Give the size a name, e.g. \"Mall of Sofia column wrap\".")
    kind = spec.get("kind")
    if kind not in KINDS:
        raise CustomFormatError("Choose whether it's print, a screen or social.")
    unit, exports = KINDS[kind]
    w = _number(spec, "w", required=True)
    h = _number(spec, "h", required=True)
    export = str(spec.get("export") or exports[0]).lower()
    if export not in exports:
        raise CustomFormatError(f"{kind.capitalize()} formats can be delivered as "
                                f"{' or '.join(e.upper() for e in exports)}.")

    # no size in the id: the file name already carries it after the id
    base = re.sub(r"[^a-z0-9-]", "-", naming.slugify(name)).strip("-")
    fid, n = base, 2
    while fid in taken_ids:
        fid, n = f"{base}-{n}", n + 1

    fmt: dict = {"id": fid, "name": name, "kind": kind}
    group = str(spec.get("group") or "").strip()
    if group:
        fmt["group"] = group
    fmt["size"] = {"w": w, "h": h, "unit": unit}
    if kind == "print":
        for key in ("bleed_mm", "safe_mm"):
            value = _number(spec, key, required=False)
            if value is not None:
                fmt[key] = value
    else:
        fmt["safe_px"] = 0
        fmt["allow_alpha"] = False
    fmt["exports"] = [export]
    notes = str(spec.get("notes") or "").strip()
    if notes:
        fmt["notes"] = notes

    try:
        validate_format(fmt)
    except RegistryError as exc:
        raise CustomFormatError(str(exc)) from exc
    return fmt


def resolve_custom(fmt: dict, registry: Registry) -> dict:
    return resolve_format(fmt, registry.print_defaults)


def _yaml_entry(fmt: dict) -> str:
    """The format as a `formats:` list item, flow-style size like the
    rest of the file (`size: {w: 400, h: 300, unit: mm}`)."""
    lines = [f"  - id: {fmt['id']}"]
    for key, value in fmt.items():
        if key == "id":
            continue
        if isinstance(value, dict):
            inner = ", ".join(f"{k}: {v}" for k, v in value.items())
            lines.append(f"    {key}: {{{inner}}}")
        elif isinstance(value, list):
            lines.append(f"    {key}: [{', '.join(str(v) for v in value)}]")
        else:
            dumped = yaml.safe_dump(value, allow_unicode=True, width=10_000).strip()
            dumped = dumped.removesuffix("\n...").removesuffix("...").strip()
            lines.append(f"    {key}: {dumped}")
    return "\n".join(lines) + "\n"


def save_format(registry_path: Path, fmt: dict) -> Registry:
    """Appends `fmt` to the end of the `formats:` list in registry.yaml
    and re-validates the whole file; restores the original if the
    result doesn't load."""
    original = registry_path.read_text(encoding="utf-8")
    entry = _yaml_entry(fmt)

    lines = original.splitlines(keepends=True)
    insert_at = len(lines)
    for i, line in enumerate(lines):
        if i > 0 and re.match(r"^[A-Za-z_]", line) and _in_formats(lines, i):
            insert_at = i
            break
    # keep the entry clear of a trailing comment block that belongs to
    # the next top-level key
    while insert_at > 0 and lines[insert_at - 1].lstrip().startswith("#"):
        insert_at -= 1
    before = "".join(lines[:insert_at]).rstrip("\n") + "\n\n"
    after = "".join(lines[insert_at:])
    updated = before + entry + ("\n" + after if after else "")

    registry_path.write_text(updated, encoding="utf-8")
    try:
        return load_registry(registry_path)
    except RegistryError:
        registry_path.write_text(original, encoding="utf-8")
        raise


def _in_formats(lines: list[str], index: int) -> bool:
    """True when the top-level key at `index` is the first one after
    `formats:` -- i.e. `formats:` is the section being closed."""
    for line in reversed(lines[:index]):
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:", line)
        if m:
            return m.group(1) == "formats"
    return False
