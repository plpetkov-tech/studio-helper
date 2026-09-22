"""Shared request context threaded through API handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from studio_helper.config import Config


@dataclass
class AppContext:
    config: Config

    @property
    def jobs_root(self) -> Path:
        return Path(self.config.jobs_root)

    @property
    def registry_path(self) -> Path:
        return Path(self.config.registry_path)
