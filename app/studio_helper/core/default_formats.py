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
NEW_SINCE_FIRST_MERGE = frozenset({"banner-pair-stacked"}) | frozenset(
    f"web-{w}x{h}" for w, h in [(1920, 1080), (1240, 280), (408, 215), (480, 480), (580, 730),
                                (745, 1322), (800, 1000), (1000, 1000), (1080, 1080)]
)

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

# Presets (job_types) added to the default after preset merging existed.
# On the first merge the older ones count as already offered.
NEW_JOB_TYPES_SINCE_FIRST_MERGE = frozenset({"web"})

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

    if not any(s.startswith("jobtype:") for s in seen):
        seen |= {"jobtype:" + n for n in _default_job_types(default_path)
                 if n not in NEW_JOB_TYPES_SINCE_FIRST_MERGE}
    for name, line in _default_job_types(default_path).items():
        if "jobtype:" + name in seen:
            continue
        try:
            if _add_job_type(user_path, name, line):
                added.append("preset " + name)
        except RegistryError:
            pass
        seen.add("jobtype:" + name)

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


def _default_job_types(default_path: Path) -> dict[str, str]:
    """{preset name: its line} from the default's job_types section."""
    out, inside = {}, False
    for line in default_path.read_text(encoding="utf-8").splitlines():
        if _TOP_LEVEL.match(line):
            inside = line.startswith("job_types:")
            continue
        m = re.match(r"^  ([\w-]+)\s*:", line)
        if inside and m:
            out[m.group(1)] = line
    return out


def _add_job_type(user_path: Path, name: str, line: str) -> bool:
    """Adds one preset line to her job_types (creating the section if
    she has none), unless she already has a preset with that name."""
    original = user_path.read_text(encoding="utf-8")
    if name in load_registry(user_path).job_types:
        return False
    lines = original.splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines) if ln.startswith("job_types:")), None)
    if start is None:
        text = original.rstrip("\n") + "\n\njob_types:\n" + line + "\n"
    else:
        end = next(
            (i for i in range(start + 1, len(lines)) if _TOP_LEVEL.match(lines[i])), len(lines)
        )
        while end - 1 > start and not lines[end - 1].strip():
            end -= 1
        if not lines[end - 1].endswith("\n"):
            lines[end - 1] += "\n"
        lines.insert(end, line + "\n")
        text = "".join(lines)
    user_path.write_text(text, encoding="utf-8")
    try:
        load_registry(user_path)
    except RegistryError:
        user_path.write_text(original, encoding="utf-8")
        raise
    return True
