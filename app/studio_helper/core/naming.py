"""Deliverable naming (SPEC.md §6.1): ASCII kebab-case slugs (with
Bulgarian Cyrillic transliteration) and the expected export filename
stem pattern.

Pattern: {slug}[_{format-id}]_{W}x{H}{unit}[_p{n}]

Just the job's name and the size (2026-10-22: management found the
names too long). The format id goes in only when two sizes of one job
would get the same name (IG story and FB story are both 1080x1920px).
There is no date and no version: a revision's file replaces the last
one under the same name. Jobs made before keep their dated names.
"""

from __future__ import annotations

import re

# Common transliteration for Bulgarian Cyrillic -> Latin (she may type
# job names in Cyrillic; filenames must stay ASCII for every tool in
# the chain). "Есенна разпродажба" -> "esenna-razprodazhba".
_CYRILLIC_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sht", "ъ": "a",
    "ь": "y", "ю": "yu", "я": "ya", "ѝ": "i",
}

MAX_SLUG_LENGTH = 40


def _transliterate(text: str) -> str:
    out = []
    for ch in text:
        replacement = _CYRILLIC_MAP.get(ch.lower())
        if replacement is None:
            out.append(ch)
        else:
            out.append(replacement.upper() if ch.isupper() else replacement)
    return "".join(out)


def slugify(text: str, max_length: int = MAX_SLUG_LENGTH) -> str:
    text = _transliterate(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text or "job"


def _fmt_dim(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value}".rstrip("0").rstrip(".")


def expected_stem(
    slug: str,
    w: float,
    h: float,
    unit: str,
    panel: int | None = None,
    format_id: str | None = None,
) -> str:
    dims = f"{_fmt_dim(w)}x{_fmt_dim(h)}{unit}"
    panel_part = f"_p{panel}" if panel is not None else ""
    id_part = f"_{format_id}" if format_id else ""
    return f"{slug}{id_part}_{dims}{panel_part}"
