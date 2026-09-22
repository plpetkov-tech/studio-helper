"""Rotating log file setup (SPEC.md §5.2: logs/, rotating, 5 x 1 MB).

Stack traces and diagnostic detail go here, never into the UI
(SPEC.md §2.5, §7).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from studio_helper import paths

_configured = False


def setup() -> logging.Logger:
    global _configured
    logger = logging.getLogger("studio_helper")
    if _configured:
        return logger

    paths.ensure_app_data_dirs()
    handler = RotatingFileHandler(
        paths.logs_dir() / "studio_helper.log",
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    _configured = True
    return logger
