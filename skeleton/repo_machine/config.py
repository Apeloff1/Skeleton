"""Fail-closed loader for .machine/repository.toml."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import stat
import tomllib

from .model import ZoneRule


MAX_CONFIG_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class MachineConfig:
    schema_version: int
    name: str
    default_owner: str
    max_files: int
    max_file_bytes: int
    max_context_bytes: int
    zones: tuple[ZoneRule, ...]
    ignore_prefixes: tuple[str, ...]
    ignore_suffixes: tuple[str, ...]
    require_tests_for_code: bool
    require_readme_for_top_level_code: bool
    detect_dependency_cycles: bool
    detect_oversized_modules: bool
    oversized_python_lines: int
    oversized_javascript_lines: int
    oversized_generic_lines: int


def _positive_int(payload: dict[str, object], name: str, default: int) -> int:
    value = payload.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def load_machine_config(root: str | Path) -> MachineConfig:
    root_path = Path(root).resolve()
    config_path = root_path / ".machine" / "repository.toml"
    try:
        info = config_path.lstat()
    except OSError as exc:
        raise ValueError("machine config is unavailable") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ValueError("machine config must be a regular non-symlink file")
    if info.st_size <= 0 or info.st_size > MAX_CONFIG_BYTES:
        raise ValueError("machine config size is outside policy")
    try:
        resolved = config_path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("machine config cannot be resolved") from exc
    if not resolved.is_relative_to(root_path):
        raise ValueError("machine config escapes repository root")
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("machine config must be a mapping")
    repository = raw.get("repository")
    policy = raw.get("policy")
    zones = raw.get("zone")
    ignore = raw.get("ignore", {})
    if not isinstance(repository, dict) or not isinstance(policy, dict):
        raise ValueError("machine config repository/policy sections are required")
    if not isinstance(zones, list) or not zones:
        raise ValueError("machine config requires zone rules")
    if not isinstance(ignore, dict):
        raise ValueError("ignore must be a mapping")

    zone_rules: list[ZoneRule] = []
    seen: set[str] = set()
    for raw_zone in zones:
        if not isinstance(raw_zone, dict):
            raise ValueError("zone entries must be mappings")
        rule = ZoneRule(
            name=raw_zone.get("name", ""),
            prefixes=tuple(raw_zone.get("prefixes", ())),
            owner=raw_zone.get("owner", repository.get("default_owner", "automation-supervisor")),
            criticality=raw_zone.get("criticality", "medium"),
        )
        if rule.name in seen:
            raise ValueError(f"duplicate zone: {rule.name}")
        seen.add(rule.name)
        zone_rules.append(rule)

    schema_version = repository.get("schema_version", 1)
    if schema_version != 1:
        raise ValueError("unsupported machine config schema")
    default_owner = repository.get("default_owner", "automation-supervisor")
    if not isinstance(default_owner, str) or not default_owner.strip():
        raise ValueError("default_owner must be text")

    prefixes = ignore.get("prefixes", ())
    suffixes = ignore.get("suffixes", ())
    if not isinstance(prefixes, list) or not isinstance(suffixes, list):
        raise ValueError("ignore lists must be arrays")

    return MachineConfig(
        schema_version=1,
        name=str(repository.get("name", root_path.name)),
        default_owner=default_owner.strip().casefold(),
        max_files=_positive_int(repository, "max_files", 50000),
        max_file_bytes=_positive_int(repository, "max_file_bytes", 2_000_000),
        max_context_bytes=_positive_int(repository, "max_context_bytes", 30_000),
        zones=tuple(zone_rules),
        ignore_prefixes=tuple(sorted({str(item) for item in prefixes if str(item)})),
        ignore_suffixes=tuple(sorted({str(item) for item in suffixes if str(item)})),
        require_tests_for_code=bool(policy.get("require_tests_for_code", True)),
        require_readme_for_top_level_code=bool(policy.get("require_readme_for_top_level_code", True)),
        detect_dependency_cycles=bool(policy.get("detect_dependency_cycles", True)),
        detect_oversized_modules=bool(policy.get("detect_oversized_modules", True)),
        oversized_python_lines=_positive_int(policy, "oversized_python_lines", 1400),
        oversized_javascript_lines=_positive_int(policy, "oversized_javascript_lines", 1800),
        oversized_generic_lines=_positive_int(policy, "oversized_generic_lines", 2400),
    )
