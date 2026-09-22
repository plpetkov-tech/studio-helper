"""Minimal path-pattern router for /api/* (SPEC.md §6.2).

Handlers register themselves with @route and return (status, payload).
Domain errors (JobError, RegistryError) become a 400 with a plain
message; anything else becomes a 500 with a generic message -- the
full exception goes to the log, never to the UI (SPEC.md §2.5, §7).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

logger = logging.getLogger("studio_helper.api")

Handler = Callable[..., tuple[int, dict]]

_ROUTES: list[tuple[str, re.Pattern, Handler]] = []


def route(method: str, pattern: str):
    regex = re.compile("^" + re.sub(r"<(\w+)>", r"(?P<\1>[^/]+)", pattern) + "$")

    def deco(fn: Handler) -> Handler:
        _ROUTES.append((method, regex, fn))
        return fn

    return deco


def dispatch(method: str, path: str, ctx, body: dict | None) -> tuple[int, dict]:
    for m, regex, fn in _ROUTES:
        if m != method:
            continue
        match = regex.match(path)
        if not match:
            continue
        try:
            return fn(ctx, body, **match.groupdict())
        except Exception as exc:  # noqa: BLE001 - convert to JSON, never a stack trace in the UI
            status = _error_status(exc)
            if status == 500:
                logger.exception("Unhandled error in %s %s", method, path)
                return 500, {"ok": False, "error": "Something went wrong. Check the log file."}
            return status, {"ok": False, "error": str(exc)}
    return 404, {"ok": False, "error": "unknown endpoint"}


def _error_status(exc: Exception) -> int:
    from studio_helper.core.job import JobError
    from studio_helper.core.registry import RegistryError

    if isinstance(exc, (JobError, RegistryError)):
        return 400
    return 500
