"""Shared request context threaded through API handlers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from studio_helper.config import Config

if TYPE_CHECKING:
    from studio_helper.poller import Poller


@dataclass
class AppContext:
    config: Config
    poller: Poller | None = None

    @property
    def jobs_root(self) -> Path:
        return Path(self.config.jobs_root)

    @property
    def registry_path(self) -> Path:
        return Path(self.config.registry_path)
