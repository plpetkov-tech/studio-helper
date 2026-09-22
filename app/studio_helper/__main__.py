"""Entry point: `python -m studio_helper` (SPEC.md §5.1, §6.2).

Normal launch: seed user data, hand off to a live instance if one
exists, otherwise start the server and open the browser. `--selftest`
proves the packaged app runs with no external installs (SPEC.md §9).
"""

from __future__ import annotations

import os
import shutil
import sys
import threading
import webbrowser

from studio_helper import config, instance, logging_setup, paths
from studio_helper.server import create_server


def seed_user_registry() -> None:
    dest = paths.user_registry_path()
    if dest.exists():
        return
    src = paths.bundled_registry_path()
    if not src.exists():
        return
    paths.ensure_app_data_dirs()
    shutil.copyfile(src, dest)


def run() -> int:
    logger = logging_setup.setup()
    logger.info("Studio Helper starting")

    live = instance.find_live_instance()
    if live is not None:
        logger.info("Live instance found on port %s, handing off", live.port)
        webbrowser.open(live.url())
        return 0

    instance.clear()
    seed_user_registry()
    config.Config.load()

    server = create_server()
    host, port = server.server_address[:2]
    info = instance.InstanceInfo(port=port, token=server.token, pid=os.getpid())
    instance.write(info)
    logger.info("Serving on http://127.0.0.1:%s", port)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    webbrowser.open(info.url())

    try:
        thread.join()
    except KeyboardInterrupt:
        server.shutdown()
    finally:
        instance.clear()
        server.server_close()

    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if "--selftest" in argv:
        from studio_helper import selftest

        return selftest.run()

    return run()


if __name__ == "__main__":
    sys.exit(main())
