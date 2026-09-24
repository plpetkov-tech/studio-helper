"""Self-update page section (SPEC.md §15, 2026-09-24): "Check for
updates" / "Download & install" on the Home page. Both run as
background tasks (SPEC.md §6.2) since they hit the network, which
nothing else in this app ever does on its own -- see updater.py.
"""

from __future__ import annotations

from studio_helper import updater

from .dispatch import route


@route("POST", "/api/update/check")
def start_update_check(ctx, body):
    task_id = ctx.tasks.start(lambda: updater.check_for_update().to_dict())
    return 200, {"ok": True, "task_id": task_id}


def _install(ctx) -> dict:
    info = updater.check_for_update()
    if not info.available:
        return {**info.to_dict(), "installed": False}

    new_dir = updater.download_and_stage(info)
    updater.schedule_relaunch(new_dir)
    return {**info.to_dict(), "installed": True}


@route("POST", "/api/update/install")
def start_update_install(ctx, body):
    task_id = ctx.tasks.start(lambda: _install(ctx))
    return 200, {"ok": True, "task_id": task_id}
