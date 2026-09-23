"""Watches each recent job's 04_export/ folder and validates files as
they land (SPEC.md §6.7). This is what makes the tool useful in
"shadow mode": it works on files exported by hand, before any
Illustrator/Photoshop/Figma automation exists (SPEC.md M2).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from studio_helper.core import job as job_mod
from studio_helper.report import write_report
from studio_helper.validators import FileResult, validate_file

logger = logging.getLogger("studio_helper.poller")

SCAN_INTERVAL_SECONDS = 2
STABLE_SCANS_REQUIRED = 2
JOB_WINDOW_DAYS = 14


@dataclass
class _FileState:
    size: int
    stable_scans: int = 1
    validated_mtime: float | None = None


class Poller:
    def __init__(self, jobs_root: Path):
        self.jobs_root = jobs_root
        self._lock = threading.Lock()
        self._file_state: dict[Path, _FileState] = {}
        self._results: dict[str, dict[str, FileResult]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def results_for(self, job_id: str) -> dict[str, FileResult]:
        with self._lock:
            return dict(self._results.get(job_id, {}))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan_once()
            except Exception:
                logger.exception("Poller scan failed")
            self._stop.wait(SCAN_INTERVAL_SECONDS)

    def scan_once(self) -> None:
        if not self.jobs_root.exists():
            return
        cutoff = datetime.now().astimezone() - timedelta(days=JOB_WINDOW_DAYS)
        for job_dir in self.jobs_root.iterdir():
            if not job_dir.is_dir() or not (job_dir / "job.json").exists():
                continue
            try:
                job = job_mod.load_job(self.jobs_root, job_dir.name)
                created = datetime.fromisoformat(job["created"])
            except (job_mod.JobError, ValueError, KeyError):
                continue
            if created < cutoff:
                continue
            self._scan_job(job_dir, job)

    def _scan_job(self, job_dir: Path, job: dict) -> None:
        export_root = job_dir / "04_export"
        if not export_root.exists():
            return

        changed = False
        seen_paths = set()

        for path in export_root.rglob("*"):
            if not path.is_file():
                continue
            seen_paths.add(path)
            stat = path.stat()

            with self._lock:
                state = self._file_state.get(path)
                if state is None or state.size != stat.st_size:
                    # New, or still growing -- wait for it to settle.
                    self._file_state[path] = _FileState(size=stat.st_size)
                    continue
                state.stable_scans += 1
                should_validate = (
                    state.stable_scans >= STABLE_SCANS_REQUIRED
                    and state.validated_mtime != stat.st_mtime
                )
                if should_validate:
                    state.validated_mtime = stat.st_mtime

            if should_validate:
                result = validate_file(path, job)
                with self._lock:
                    self._results.setdefault(job["id"], {})[str(path)] = result
                changed = True

        with self._lock:
            stale_state = [
                p
                for p in self._file_state
                if export_root in p.parents and p not in seen_paths
            ]
            for p in stale_state:
                del self._file_state[p]

            job_results = self._results.get(job["id"], {})
            stale_results = [p for p in job_results if Path(p) not in seen_paths]
            for p in stale_results:
                del job_results[p]
                changed = True

        if changed:
            with self._lock:
                results_snapshot = dict(self._results.get(job["id"], {}))
            write_report(job_dir, job, results_snapshot)
