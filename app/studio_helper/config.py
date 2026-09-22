"""config.json under %APPDATA%\\StudioHelper (SPEC.md §5.2)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from studio_helper import paths


@dataclass
class Config:
    jobs_root: str = field(default_factory=lambda: str(paths.default_jobs_root()))
    registry_path: str = field(default_factory=lambda: str(paths.user_registry_path()))
    last_opened_jobs: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> Config:
        path = paths.config_path()
        if not path.exists():
            cfg = cls()
            cfg.save()
            return cfg
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self) -> None:
        paths.ensure_app_data_dirs()
        paths.config_path().write_text(
            json.dumps(asdict(self), indent=2), encoding="utf-8"
        )
