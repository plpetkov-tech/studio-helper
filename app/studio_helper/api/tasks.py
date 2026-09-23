"""Long actions (COM calls) run in a worker thread; the UI polls
/api/tasks/<id> for the result (SPEC.md §6.2). Illustrator can take
up to two minutes to cold-start (SPEC.md §6.3), far too long to hold
an HTTP request open for.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from .dispatch import route


@dataclass
class Task:
    id: str
    status: str = "running"  # running | done | error
    result: dict | None = None
    error: str | None = None


class TaskManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, Task] = {}

    def start(self, fn: Callable[[], dict]) -> str:
        task_id = uuid.uuid4().hex
        task = Task(id=task_id)
        with self._lock:
            self._tasks[task_id] = task

        def _run() -> None:
            try:
                result = fn()
                with self._lock:
                    task.status = "done"
                    task.result = result
            except Exception as exc:  # noqa: BLE001 - reported via polling, never a stack trace in the UI
                with self._lock:
                    task.status = "error"
                    task.error = str(exc)

        threading.Thread(target=_run, daemon=True).start()
        return task_id

    def get(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)


@route("GET", "/api/tasks/<task_id>")
def get_task(ctx, body, task_id):
    task = ctx.tasks.get(task_id)
    if task is None:
        return 404, {"ok": False, "error": "unknown task"}
    if task.status == "running":
        return 200, {"ok": True, "status": "running"}
    if task.status == "error":
        return 200, {"ok": True, "status": "error", "error": task.error}
    return 200, {"ok": True, "status": "done", "result": task.result}
