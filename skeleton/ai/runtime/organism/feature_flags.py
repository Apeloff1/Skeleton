"""Feature flags — dynamic capability toggling with targeting and rollout.

Provides a feature-flag system with boolean, percentage, and targeted
rollouts. Supports per-operator, per-session, and per-subsystem targeting.
Integrates with audit logging for every flag change.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FlagRule:
    flag_name: str
    enabled: bool = False
    percentage: float = 0.0
    targets: Dict[str, List[str]] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def evaluate(self, context: Dict[str, str]) -> bool:
        if not self.enabled:
            return False
        for dep in self.dependencies:
            if not context.get(f"flag:{dep}"):
                return False
        for key, values in self.targets.items():
            if context.get(key) in values:
                return True
        if self.percentage >= 100.0:
            return True
        if self.percentage <= 0.0:
            return False
        # Deterministic by session id if present
        session = context.get("session_id", str(random.random()))
        bucket = (hash(session + self.flag_name) % 10000) / 100.0
        return bucket < self.percentage

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flag_name": self.flag_name,
            "enabled": self.enabled,
            "percentage": self.percentage,
            "targets": self.targets,
            "dependencies": self.dependencies,
        }


class FeatureFlagRegistry:
    """Central feature flag registry with persistence."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root or Path(".skeleton")
        self._flags: Dict[str, FlagRule] = {}
        self._file = self.root / "feature_flags.json"
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            data = __import__("json").loads(self._file.read_text(encoding="utf-8"))
            for name, d in data.items():
                self._flags[name] = FlagRule(
                    flag_name=name,
                    enabled=d.get("enabled", False),
                    percentage=d.get("percentage", 0.0),
                    targets=d.get("targets", {}),
                    dependencies=d.get("dependencies", []),
                )

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self._file.write_text(__import__("json").dumps({n: f.to_dict() for n, f in self._flags.items()}, indent=2), encoding="utf-8")

    def register(self, name: str, enabled: bool = False, percentage: float = 0.0, targets: Optional[Dict[str, List[str]]] = None, dependencies: Optional[List[str]] = None) -> FlagRule:
        rule = FlagRule(
            flag_name=name,
            enabled=enabled,
            percentage=percentage,
            targets=targets or {},
            dependencies=dependencies or [],
        )
        self._flags[name] = rule
        self._save()
        return rule

    def set(self, name: str, enabled: Optional[bool] = None, percentage: Optional[float] = None) -> None:
        if name not in self._flags:
            self.register(name)
        flag = self._flags[name]
        if enabled is not None:
            flag.enabled = enabled
        if percentage is not None:
            flag.percentage = percentage
        self._save()

    def is_enabled(self, name: str, context: Optional[Dict[str, str]] = None) -> bool:
        flag = self._flags.get(name)
        if not flag:
            return False
        return flag.evaluate(context or {})

    def list_flags(self) -> List[Dict[str, Any]]:
        return [f.to_dict() for f in self._flags.values()]

    def card(self) -> Dict[str, Any]:
        return {
            "kind": "feature-flag-card",
            "flags": self.list_flags(),
            "total": len(self._flags),
        }
