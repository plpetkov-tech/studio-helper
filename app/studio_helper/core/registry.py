"""Registry loading, schema validation with file+line errors, and
format/job-type resolution (SPEC.md §6.1).

Errors always name the file and, where we can locate it, the line --
composing the YAML into a Node tree (instead of just parsing it) lets
us walk the same path a jsonschema error reports and read that node's
source line, without a second YAML-with-line-numbers dependency.
"""

from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import jsonschema
import yaml
from jsonschema.exceptions import best_match

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "registry.schema.json"

PRINT_DEFAULT_FIELDS = [
    "bleed_mm",
    "safe_mm",
    "pdf_preset",
    "raster_ppi",
    "min_image_ppi",
    "tiff_if_longest_side_mm_over",
    "tiff_ppi",
]


class RegistryError(Exception):
    """A registry.yaml problem, with enough location info to fix it."""

    def __init__(self, message: str, path: Path | None = None, line: int | None = None):
        self.registry_path = path
        self.line = line
        location = ""
        if path is not None:
            location = str(path) + (f":{line}" if line else "")
        super().__init__(f"{location}: {message}" if location else message)


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _resolve_node(root: yaml.Node, path: list) -> yaml.Node:
    node = root
    for key in path:
        if isinstance(node, yaml.MappingNode):
            match = None
            for k_node, v_node in node.value:
                if k_node.value == str(key):
                    match = v_node
                    break
            if match is None:
                return node
            node = match
        elif isinstance(node, yaml.SequenceNode):
            if not isinstance(key, int) or key >= len(node.value):
                return node
            node = node.value[key]
        else:
            return node
    return node


def _line_for_key(container: yaml.Node, key: str) -> int:
    if isinstance(container, yaml.MappingNode):
        for k_node, _v_node in container.value:
            if k_node.value == key:
                return k_node.start_mark.line + 1
    return container.start_mark.line + 1


def _unexpected_keys(message: str) -> list[str]:
    return re.findall(r"'([^']+)'", message)


def load_registry(path: Path) -> Registry:
    if not path.exists():
        raise RegistryError("Registry file not found.", path)

    text = path.read_text(encoding="utf-8")

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        line = (mark.line + 1) if mark is not None else None
        raise RegistryError(str(exc).splitlines()[0], path, line) from exc

    if data is None:
        raise RegistryError("Registry file is empty.", path, 1)
    if not isinstance(data, dict):
        raise RegistryError("Registry file must be a YAML mapping at the top level.", path, 1)

    schema = _load_schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)

    errors = list(validator.iter_errors(data))
    if errors:
        err = best_match(errors)
        path_list = list(err.path)
        root_node = yaml.compose(text)
        container_node = _resolve_node(root_node, path_list)

        if err.validator == "additionalProperties":
            keys = _unexpected_keys(err.message)
            line = (
                _line_for_key(container_node, keys[0])
                if keys
                else container_node.start_mark.line + 1
            )
        else:
            line = container_node.start_mark.line + 1

        location = "/".join(str(p) for p in path_list) or "(top level)"
        raise RegistryError(f"{err.message} (at {location})", path, line)

    return Registry.from_data(data, path)


@dataclass(frozen=True)
class Registry:
    version: int
    print_defaults: dict
    formats: dict = field(default_factory=dict)
    job_types: dict = field(default_factory=dict)
    source_path: Path | None = None

    @classmethod
    def from_data(cls, data: dict, path: Path) -> Registry:
        print_defaults = data.get("print_defaults", {})
        formats: dict[str, dict] = {}

        for fmt in data["formats"]:
            fid = fmt["id"]
            if fid in formats:
                raise RegistryError(f"Duplicate format id '{fid}'.", path)

            resolved = dict(fmt)
            if resolved.get("kind") == "print":
                for f in PRINT_DEFAULT_FIELDS:
                    if f not in resolved and f in print_defaults:
                        resolved[f] = print_defaults[f]
            resolved.setdefault("scale", 1)
            resolved.setdefault("allow_alpha", False)
            formats[fid] = resolved

        return cls(
            version=data["version"],
            print_defaults=print_defaults,
            formats=formats,
            job_types=data.get("job_types", {}),
            source_path=path,
        )

    def resolve_job_type(self, name: str) -> list[str]:
        patterns = self.job_types.get(name)
        if patterns is None:
            raise RegistryError(f"Unknown job type '{name}'.", self.source_path)

        matched: list[str] = []
        for pattern in patterns:
            for fid in self.formats:
                if fnmatch.fnmatch(fid, pattern) and fid not in matched:
                    matched.append(fid)
        return matched
