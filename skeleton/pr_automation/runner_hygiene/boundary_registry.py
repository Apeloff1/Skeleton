"""Live-service test boundary registry helpers (Pack E).

Wraps the fail-closed Backend Test boundary contract so control-plane
hygiene can load, validate, and audit the registry without weakening it.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_MANIFEST = Path("backend/tests/live_service_tests.json")
CHECKER = Path("backend/scripts/check_live_service_test_boundaries.py")


@dataclass(frozen=True, slots=True)
class BoundaryRegistry:
    """Immutable view of the live-service test registry."""

    version: int
    tests: Mapping[str, Mapping[str, str]]
    path: str

    @property
    def size(self) -> int:
        return len(self.tests)

    def requires(self, name: str) -> bool:
        return name in self.tests


def load_live_service_manifest(path: Path | str = DEFAULT_MANIFEST) -> BoundaryRegistry:
    p = Path(path)
    raw: Any = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("live-service manifest must use version 1")
    tests = raw.get("tests")
    if not isinstance(tests, dict) or not tests:
        raise ValueError("live-service manifest must contain a non-empty tests mapping")
    normalized: dict[str, dict[str, str]] = {}
    for name, meta in tests.items():
        if not isinstance(name, str) or not name.startswith("test_") or not name.endswith(".py"):
            raise ValueError(f"invalid live-service test name: {name!r}")
        if not isinstance(meta, dict):
            raise ValueError(f"{name}: metadata must be an object")
        reason = meta.get("reason")
        target = meta.get("target")
        if not isinstance(reason, str) or len(reason.strip()) < 20:
            raise ValueError(f"{name}: reason must be descriptive")
        if not isinstance(target, str) or not target.strip():
            raise ValueError(f"{name}: target must be non-empty text")
        normalized[name] = {"reason": reason.strip(), "target": target.strip()}
    return BoundaryRegistry(version=1, tests=normalized, path=str(p))


def audit_live_service_boundaries(*, root: Path | str = ".") -> tuple[str, ...]:
    """Run the repository fail-closed checker and return findings (empty = pass)."""
    root_path = Path(root).resolve()
    checker = root_path / CHECKER
    if not checker.is_file():
        raise FileNotFoundError(f"missing boundary checker: {checker}")
    spec = importlib.util.spec_from_file_location("live_service_boundary_checker", checker)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to load boundary checker: {checker}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    audit = getattr(mod, "audit", None)
    if not callable(audit):
        raise AttributeError("boundary checker missing audit()")
    return tuple(audit())


__all__ = [
    "BoundaryRegistry",
    "DEFAULT_MANIFEST",
    "audit_live_service_boundaries",
    "load_live_service_manifest",
]
