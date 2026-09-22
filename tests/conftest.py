"""SPEC.md §9: Adobe E2E tests only run on the owner's Windows machine
with Illustrator/Photoshop, opted in via STUDIO_HELPER_ADOBE=1.
"""

import os

import pytest


def pytest_collection_modifyitems(config, items):
    if os.environ.get("STUDIO_HELPER_ADOBE") == "1":
        return
    skip_adobe = pytest.mark.skip(
        reason="set STUDIO_HELPER_ADOBE=1 on a machine with Illustrator/Photoshop"
    )
    for item in items:
        if "adobe" in item.keywords:
            item.add_marker(skip_adobe)
