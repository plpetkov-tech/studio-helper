"""Maps a job's deliverables to validated files, or "missing" (SPEC.md
§6.8). Shared by the API, the poller's report.html, and the Job page.
"""

from __future__ import annotations

from pathlib import Path

from studio_helper.validators import FileResult


def match_result(deliverable: dict, results: dict[str, FileResult]) -> FileResult | None:
    for result in results.values():
        rd = result.deliverable
        if (
            rd is not None
            and rd.get("expected_stem") == deliverable["expected_stem"]
            and rd.get("type") == deliverable["type"]
        ):
            return result
    return None


def deliverables_table(job: dict, results: dict[str, FileResult]) -> list[dict]:
    """One row per expected deliverable, each carrying its validated
    status ("ok"/"warn"/"fail") and checks, or "missing" with none."""
    rows = []
    for deliverable in job.get("deliverables", []):
        result = match_result(deliverable, results)
        if result is not None:
            rows.append(
                {
                    **deliverable,
                    "status": result.status,
                    "found_file": Path(result.path).name,
                    "checks": [
                        {"id": c.id, "status": c.status, "message": c.message, "hint": c.hint}
                        for c in result.checks
                    ],
                }
            )
        else:
            rows.append({**deliverable, "status": "missing", "found_file": None, "checks": []})
    return collapse_alternatives(rows)


DIGITAL_TYPES = ("png", "jpg", "mp4")


def collapse_alternatives(rows: list[dict]) -> list[dict]:
    """A digital format listing several exports ([jpg, png], [jpg, mp4])
    accepts any one of them -- Photoshop writes just one. Show one row
    per artboard: the delivered file(s) if any arrived, else the first
    listed type, carrying the others as `alternatives`."""
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        if row["type"] in DIGITAL_TYPES:
            groups.setdefault((row["format_id"], row.get("panel")), []).append(row)

    out = []
    for row in rows:
        group = groups.get((row["format_id"], row.get("panel")))
        if row["type"] not in DIGITAL_TYPES or group is None or len(group) == 1:
            out.append(row)
            continue
        found = [r for r in group if r["status"] != "missing"]
        if found:
            if row["status"] != "missing":
                out.append(row)
        elif row is group[0]:
            out.append({**row, "alternatives": [r["type"] for r in group[1:]]})
    return out
