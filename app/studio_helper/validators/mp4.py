"""MP4 validator (SPEC.md §6.7): a stub for v1. Video validation and
rendering are out of scope until a later phase (SPEC.md §3)."""

from __future__ import annotations

from pathlib import Path

from .model import Check


def validate(path: Path, fmt: dict, deliverable: dict) -> list[Check]:
    return [Check("video", "warn", "Video checks not available yet.")]
