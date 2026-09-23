"""SPEC.md §9: if tests/fixtures/real/ has real samples with an
expected.yaml (see the README there), validate them for real and
compare against what the owner recorded. Skipped -- not failed --
when there's nothing there, which is the normal state for anyone
without real client samples locally (the folder is gitignored).
"""

from pathlib import Path

import pytest
import yaml
from studio_helper.validators import validate_file

REAL_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "real"


def _load_expectations() -> dict:
    expected_path = REAL_DIR / "expected.yaml"
    if not expected_path.exists():
        return {}
    return yaml.safe_load(expected_path.read_text(encoding="utf-8")) or {}


def test_real_samples_match_expectations():
    expectations = _load_expectations()
    if not expectations:
        pytest.skip("no tests/fixtures/real/expected.yaml -- see tests/fixtures/real/README.md")

    failures = []
    for filename, spec in expectations.items():
        path = REAL_DIR / filename
        if not path.exists():
            failures.append(f"{filename}: listed in expected.yaml but the file is missing")
            continue

        job = {"formats": [spec["format"]], "deliverables": [spec["deliverable"]]}
        result = validate_file(path, job)
        if result.status != spec["status"]:
            messages = "; ".join(f"{c.id}={c.status}" for c in result.checks)
            failures.append(
                f"{filename}: expected status '{spec['status']}', "
                f"got '{result.status}' ({messages})"
            )

    assert not failures, "\n".join(failures)
