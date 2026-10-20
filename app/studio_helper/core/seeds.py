"""Which existing size a newly added size starts from (ROADMAP R3).

A size added to a campaign later doesn't start empty: it gets a scaled
copy of her artwork from the existing size with the closest shape, on a
"Starting point - adjust me" layer. This module only picks the pairs;
the app adapters do the copying.
"""

from __future__ import annotations

import math


def _family(fmt: dict) -> str:
    return "print" if fmt.get("kind") == "print" else "digital"


def aspect(fmt: dict) -> float:
    return fmt["size"]["w"] / fmt["size"]["h"]


def _area(fmt: dict) -> float:
    return fmt["size"]["w"] * fmt["size"]["h"]  # physical size: same unit within a family


def closest_source(target: dict, candidates: list[dict]) -> dict | None:
    """The candidate of the same family (print or digital) whose shape is
    closest to the target's, by |log(aspect ratio)|; on a tie the larger
    one, since scaling down keeps more detail than scaling up. Panel
    formats are never paired: their pieces don't map one to one."""
    if target.get("panels") or "size" not in target:
        return None
    pool = [c for c in candidates
            if c["id"] != target["id"] and not c.get("panels") and "size" in c
            and _family(c) == _family(target)]
    if not pool:
        return None
    want = math.log(aspect(target))
    return min(pool, key=lambda c: (round(abs(math.log(aspect(c)) - want), 6), -_area(c)))


def seeds_for(job: dict, new_ids: list[str]) -> list[dict]:
    """[{target, source}] for the sizes in `new_ids`, each paired with the
    closest size that was already in the job."""
    existing = [f for f in job["formats"] if f["id"] not in new_ids]
    pairs = []
    for fmt in job["formats"]:
        if fmt["id"] not in new_ids:
            continue
        source = closest_source(fmt, existing)
        if source is not None:
            pairs.append({"target": fmt["id"], "source": source["id"]})
    return pairs
