"""Shared result types for every validator (SPEC.md §6.7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

STATUS_RANK = {"ok": 0, "warn": 1, "fail": 2}


@dataclass
class Check:
    id: str
    status: str  # "ok" | "warn" | "fail"
    message: str
    hint: str = ""


@dataclass
class FileResult:
    path: Path
    format_id: str | None
    deliverable: dict | None
    status: str
    checks: list[Check] = field(default_factory=list)


def overall_status(checks: list[Check]) -> str:
    if not checks:
        return "ok"
    return max((c.status for c in checks), key=lambda s: STATUS_RANK.get(s, 0))
