"""Deliverable naming (SPEC.md §6.1): ASCII kebab-case slugs (with
Bulgarian Cyrillic transliteration) and the expected export filename
stem pattern.

Pattern: {date}_{slug}_{format-id}_{W}x{H}{unit}[_p{n}]_v{NN}
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
    date: str,
    slug: str,
    format_id: str,
    w: float,
    h: float,
    unit: str,
    version: int,
    panel: int | None = None,
) -> str:
    dims = f"{_fmt_dim(w)}x{_fmt_dim(h)}{unit}"
    panel_part = f"_p{panel}" if panel is not None else ""
    return f"{date}_{slug}_{format_id}_{dims}{panel_part}_v{version:02d}"
