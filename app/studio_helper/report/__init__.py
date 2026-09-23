"""report.html generator (SPEC.md §6.7): a static, self-contained
summary of a job's deliverables, written by the poller every time a
validated file's result changes. "Self-contained" means every style
is inline -- it must open correctly as a standalone file (double-
clicked, emailed, dropped in a chat), with no dependency on the
running server.
"""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

from studio_helper.deliverables import deliverables_table
from studio_helper.validators import FileResult

_STATUS_LABEL = {
    "ok": "✓ ok",
    "warn": "⚠ warning",
    "fail": "✗ fail",
    "missing": "✗ missing",
}

_CSS = """
body { font-family: -apple-system, "Segoe UI", Arial, sans-serif; color: #22262b;
       background: #fafafa; margin: 0; padding: 32px; }
main { max-width: 900px; margin: 0 auto; }
h1 { font-size: 24px; margin-bottom: 4px; }
.meta { color: #6b7280; margin-bottom: 20px; }
table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px;
        overflow: hidden; border: 1px solid #e5e7eb; }
th, td { text-align: left; padding: 10px 14px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }
th { color: #6b7280; font-weight: 600; font-size: 12px; text-transform: uppercase; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 999px;
         font-size: 13px; font-weight: 600; }
.badge.ok { color: #16a34a; background: #ecfdf3; }
.badge.warn { color: #b45309; background: #fffbeb; }
.badge.fail, .badge.missing { color: #b91c1c; background: #fef2f2; }
ul.checks { margin: 4px 0 0; padding-left: 18px; font-size: 13px; }
ul.checks li.ok { color: #16a34a; }
ul.checks li.warn { color: #b45309; }
ul.checks li.fail { color: #b91c1c; }
.hint { color: #6b7280; }
"""


def _row_html(row: dict) -> str:
    status = row["status"]
    filename = row["found_file"] or "(not exported yet)"
    checks_html = ""
    if row["checks"]:
        items = "".join(
            f"<li class='{html.escape(c['status'])}'><strong>{html.escape(c['status'])}</strong> "
            f"{html.escape(c['message'])}"
            + (f" <span class='hint'>{html.escape(c['hint'])}</span>" if c["hint"] else "")
            + "</li>"
            for c in row["checks"]
        )
        checks_html = f"<ul class='checks'>{items}</ul>"

    panel = f" (panel {row['panel']})" if row.get("panel") else ""
    return (
        "<tr>"
        f"<td>{html.escape(row['expected_stem'])}.{html.escape(row['type'])}</td>"
        f"<td>{html.escape(row['format_id'])}{panel}</td>"
        f"<td>{html.escape(filename)}</td>"
        f"<td><span class='badge {html.escape(status)}'>{_STATUS_LABEL.get(status, status)}</span>"
        f"{checks_html}</td>"
        "</tr>"
    )


def render_report(job: dict, results: dict[str, FileResult]) -> str:
    rows = deliverables_table(job, results)
    done = sum(1 for r in rows if r["status"] in ("ok", "warn"))
    total = len(rows)
    generated = datetime.now().astimezone().isoformat(timespec="seconds")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(job['name'])} report</title>
<style>{_CSS}</style>
</head>
<body>
<main>
  <h1>{html.escape(job['name'])}</h1>
  <p class="meta">
    Job {html.escape(job['id'])} &middot; version {job['version']} &middot;
    {done} / {total} deliverables ready &middot; generated {generated}
  </p>
  <table>
    <thead><tr><th>Expected file</th><th>Format</th><th>Found file</th><th>Status</th></tr></thead>
    <tbody>{"".join(_row_html(r) for r in rows)}</tbody>
  </table>
</main>
</body>
</html>"""


def write_report(job_dir: Path, job: dict, results: dict[str, FileResult]) -> Path:
    path = job_dir / "report.html"
    path.write_text(render_report(job, results), encoding="utf-8")
    return path
