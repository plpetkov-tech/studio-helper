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
    return rows
