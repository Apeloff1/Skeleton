"""Configuration snapshots — versioned, validated, rollback-able kernel config.

Kernel behaviour is driven by config that agents can tune at runtime
(budgets, watermarks, TTLs). Untracked mutation means nobody can answer
"what changed before the incident?" — and a bad push has no way back.

- :class:`ConfigSnapshot` — an immutable, hash-stamped version of the
  full config map, chained to its parent like the merkle log.
- :class:`ConfigStore` — ``propose`` validates a candidate against
  registered per-key validators before it can become active; ``activate``
  makes it current; ``rollback`` walks the chain to any earlier version.
  Every transition is appended to an audit trail with actor + reason.
- Diffing is first-class: :meth:`diff` reports added/removed/changed
  keys between any two versions, so review happens on deltas, not vibes.

Zero deps; values must be JSON-serialisable so snapshots can ship on
wire and anchor into the merkle log.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .errors import ConfigurationError


def _canonical(data: Mapping[str, Any]) -> str:
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(
            "config values must be JSON-serialisable",
            context={"error": str(exc)},
        ) from exc


@dataclass(frozen=True)
class ConfigSnapshot:
    version: int
    values: Mapping[str, Any]
    parent_digest: Optional[str]
    digest: str
    actor: str
    reason: str
    created_at: float

    @classmethod
    def build(cls, version: int, values: Mapping[str, Any],
              parent_digest: Optional[str], actor: str,
              reason: str, created_at: float) -> "ConfigSnapshot":
        body = _canonical(values)
        digest = hashlib.sha256(
            f"{version}|{parent_digest or '-'}|{body}".encode()).hexdigest()
        return cls(version, dict(values), parent_digest, digest,
                   actor, reason, created_at)


@dataclass(frozen=True)
class AuditEntry:
    version: int
    action: str           # propose / activate / rollback / reject
    actor: str
    reason: str
    at: float


class ConfigStore:
    """Versioned config with validation and rollback."""

    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self._now = clock or time.time
        self._validators: Dict[str, Callable[[Any], Optional[str]]] = {}
        self._history: List[ConfigSnapshot] = []
        self._active_index: int = -1
        self._audit: List[AuditEntry] = []

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    def register_validator(self, key: str,
                           check: Callable[[Any], Optional[str]]) -> None:
        """check(value) -> None if valid, else an error message string."""
        self._validators[key] = check

    def _validate(self, values: Mapping[str, Any]) -> List[str]:
        problems = []
        for key, check in self._validators.items():
            if key in values:
                problem = check(values[key])
                if problem:
                    problems.append(f"{key}: {problem}")
        _canonical(values)  # raises on non-serialisable
        return problems

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def propose(self, values: Mapping[str, Any], *, actor: str,
                reason: str) -> ConfigSnapshot:
        problems = self._validate(values)
        if problems:
            self._audit.append(AuditEntry(
                version=-1, action="reject", actor=actor,
                reason="; ".join(problems), at=self._now()))
            raise ConfigurationError(
                "config candidate failed validation",
                context={"problems": tuple(problems)},
            )
        parent = self._history[self._active_index] if self._active_index >= 0 else None
        snap = ConfigSnapshot.build(
            version=(parent.version + 1 if parent else 1),
            values=values,
            parent_digest=parent.digest if parent else None,
            actor=actor, reason=reason, created_at=self._now())
        self._history.append(snap)
        self._audit.append(AuditEntry(snap.version, "propose", actor,
                                      reason, self._now()))
        return snap

    def activate(self, snapshot: ConfigSnapshot) -> ConfigSnapshot:
        try:
            idx = self._history.index(snapshot)
        except ValueError as exc:
            raise ConfigurationError("unknown snapshot",
                                     context={"digest": snapshot.digest}) from exc
        self._active_index = idx
        self._audit.append(AuditEntry(snapshot.version, "activate",
                                      snapshot.actor, snapshot.reason,
                                      self._now()))
        return snapshot

    def rollback(self, to_version: int, *, actor: str,
                 reason: str) -> ConfigSnapshot:
        for idx, snap in enumerate(self._history):
            if snap.version == to_version:
                self._active_index = idx
                self._audit.append(AuditEntry(to_version, "rollback",
                                              actor, reason, self._now()))
                return snap
        raise ConfigurationError("no snapshot at that version",
                                 context={"version": to_version})

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def active(self) -> Optional[ConfigSnapshot]:
        return self._history[self._active_index] if self._active_index >= 0 else None

    def get(self, key: str, default: Any = None) -> Any:
        snap = self.active()
        return snap.values.get(key, default) if snap else default

    def diff(self, from_version: int, to_version: int) -> Dict[str, Any]:
        a = self._find(from_version)
        b = self._find(to_version)
        added = {k: b.values[k] for k in b.values.keys() - a.values.keys()}
        removed = tuple(sorted(a.values.keys() - b.values.keys()))
        changed = {
            k: {"from": a.values[k], "to": b.values[k]}
            for k in a.values.keys() & b.values.keys()
            if a.values[k] != b.values[k]
        }
        return {"added": added, "removed": removed, "changed": changed,
                "from": from_version, "to": to_version}

    def audit_trail(self) -> Tuple[AuditEntry, ...]:
        return tuple(self._audit)

    def _find(self, version: int) -> ConfigSnapshot:
        for snap in self._history:
            if snap.version == version:
                return snap
        raise ConfigurationError("no snapshot at that version",
                                 context={"version": version})
