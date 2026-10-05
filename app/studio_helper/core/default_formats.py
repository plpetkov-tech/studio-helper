"""New formats from the shipped default registry, added to her own
registry.yaml on startup.

Her registry is hers: once she has edited it, an update never replaces
it (__main__.seed_user_registry only swaps out untouched copies). But
formats added to the default later (e.g. the TEODOR banner pair) should
still reach her. So each default format she doesn't have is copied in,
as the default file's own text (comments included), at the end of her
`formats:` list. Every default id offered is remembered, so a format
she deletes on purpose isn't added back by the next start.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from studio_helper.core.custom_formats import insert_entry_text
from studio_helper.core.registry import RegistryError, load_registry

# Defaults added after the last release that shipped the registry as a
# whole file (v0.4.2). On the very first merge everything else counts as
# already offered, so formats she removed back then stay removed.
NEW_SINCE_FIRST_MERGE = frozenset({"banner-pair-stacked"})

# One-time changes to formats she already has. Each runs once (its name
# is remembered with the offered ids) and only fills a field her entry
# doesn't set -- a value she chose herself always wins.
FIELD_PATCHES = [
    # The print shop asked for ~275 MB TIFFs; 150 ppi at 4 m made ~1.8 GB.
    ("idea-vinyl-tiff-60ppi", "tiff_ppi", 60, (
        "mall-print-idea-vinyl-4020x3050",
        "mall-print-idea-vinyl-4000x3000",
        "mall-print-idea-vinyl-4100x3100",
    )),
]

_ENTRY = re.compile(r"^  - id: (\S+)")
_TOP_LEVEL = re.compile(r"^[A-Za-z_]")


def default_entries(text: str) -> dict[str, str]:
    """{format id: its text block}, in file order. A block starts at the
    comment lines right above `  - id:` and runs to the next one."""
    lines = text.splitlines(keepends=True)
    try:
        start = next(i for i, ln in enumerate(lines) if re.match(r"^formats\s*:", ln))
    except StopIteration:
        return {}
    end = next((i for i in range(start + 1, len(lines)) if _TOP_LEVEL.match(lines[i])), len(lines))

    def block_start(i: int) -> int:
        while i - 1 > start and lines[i - 1].startswith("  #"):
            i -= 1
        return i

    heads = [(i, m.group(1)) for i in range(start + 1, end) if (m := _ENTRY.match(lines[i]))]
    starts = [block_start(i) for i, _ in heads]
    blocks = {}
    for n, (_i, fid) in enumerate(heads):
        stop = starts[n + 1] if n + 1 < len(heads) else end
        chunk = lines[starts[n]:stop]
        last = n + 1 == len(heads)
        while chunk and (not chunk[-1].strip() or (last and chunk[-1].startswith("#"))):
            chunk.pop()
        blocks[fid] = "".join(chunk)
    return blocks


def merge_new_defaults(user_path: Path, default_path: Path, seen_path: Path) -> list[str]:
    """Adds default formats she hasn't been offered yet and doesn't
    have. Returns the ids added. Leaves everything alone if her
    registry doesn't load (Setup check / Formats will say why)."""
    if not user_path.exists() or not default_path.exists():
        return []
    entries = default_entries(default_path.read_text(encoding="utf-8"))
    try:
        seen = set(json.loads(seen_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        seen = set(entries) - NEW_SINCE_FIRST_MERGE
    try:
        have = set(load_registry(user_path).formats)
    except RegistryError:
        return []

    added, failed = [], set()
    for fid, block in entries.items():
        if fid in seen or fid in have:
            continue
        try:
            insert_entry_text(user_path, block)
            added.append(fid)
        except RegistryError:
            failed.add(fid)  # e.g. clashes with something of hers; offer it again next time
    seen |= set(entries) - failed

    for name, key, value, ids in FIELD_PATCHES:
        if "patch:" + name in seen:
            continue
        for fid in ids:
            try:
                if _set_missing_field(user_path, fid, key, value):
                    added.append(f"{fid}.{key}")
            except RegistryError:
                pass  # leave her file as it was (restored), don't retry forever
        seen.add("patch:" + name)

    seen_path.write_text(json.dumps(sorted(seen)), encoding="utf-8")
    return added


def _set_missing_field(user_path: Path, fid: str, key: str, value) -> bool:
    """Adds `key: value` to format `fid` in her file if that entry
    doesn't set it. Re-validates; restores the file on failure."""
    original = user_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    pattern = re.compile(rf"^  - id: {re.escape(fid)}\s*$")
    head = next((i for i, ln in enumerate(lines) if pattern.match(ln)), None)
    if head is None:
        return False
    i = head + 1
    while i < len(lines) and lines[i].startswith("    "):
        if re.match(rf"^    {re.escape(key)}\s*:", lines[i]):
            return False  # she set it herself
        i += 1
    lines.insert(head + 1, f"    {key}: {value}\n")
    user_path.write_text("".join(lines), encoding="utf-8")
    try:
        load_registry(user_path)
    except RegistryError:
        user_path.write_text(original, encoding="utf-8")
        raise
    return True
