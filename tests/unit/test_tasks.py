import threading
import time

from studio_helper.api.tasks import TaskManager


def test_get_unknown_task_returns_none():
    assert TaskManager().get("nope") is None


def test_successful_task_reports_done():
    manager = TaskManager()
    task_id = manager.start(lambda: {"value": 42})
    for _ in range(50):
        task = manager.get(task_id)
        if task.status != "running":
            break
        time.sleep(0.01)
    assert task.status == "done"
    assert task.result == {"value": 42}


def test_failing_task_reports_error():
    def boom():
        raise RuntimeError("kaboom")

    manager = TaskManager()
    task_id = manager.start(boom)
    for _ in range(50):
        task = manager.get(task_id)
        if task.status != "running":
            break
        time.sleep(0.01)
    assert task.status == "error"
    assert "kaboom" in task.error


def test_task_starts_as_running():
    manager = TaskManager()
    started = threading.Event()
    proceed = threading.Event()

    def slow():
        started.set()
        proceed.wait(2)
        return {}

    task_id = manager.start(slow)
    started.wait(2)
    assert manager.get(task_id).status == "running"
    proceed.set()
