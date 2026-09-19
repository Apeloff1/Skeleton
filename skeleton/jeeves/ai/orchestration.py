"""Deterministic Jeeves orchestration records.

This plane models authority and dependency ordering only.  It deliberately does not
execute tools, shell commands, providers, or workers.  Supervisor plans may delegate
to Secretary plans; Secretary plans may delegate to Workers.  Reverse delegation is
rejected so this module cannot become a second authority hierarchy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .contracts import Authority, MAX_EVIDENCE, MAX_TEXT

MAX_TASKS = 512
MAX_DEPENDENCIES = 64
MAX_METADATA_BYTES = 32 * 1024


class OrchestrState(str, Enum):
    NEW = "new"
    READY = "ready"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


_ALLOWED_DELEGATION = {
    Authority.SUPERVISOR: frozenset({Authority.SUPERVISOR, Authority.SECRETARY, Authority.WORKER}),
    Authority.SECRETARY: frozenset({Authority.SECRETARY, Authority.WORKER}),
    Authority.WORKER: frozenset({Authority.WORKER}),
}


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_TEXT or "\x00" in value:
        raise ValueError(f"invalid {name}")
    return value


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("metadata must be a mapping")
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        detached = json.loads(encoded)
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata must be finite JSON") from exc
    if len(encoded.encode()) > MAX_METADATA_BYTES:
        raise ValueError("metadata too large")
    if not all(isinstance(k, str) and k and len(k) <= MAX_TEXT for k in detached):
        raise ValueError("invalid metadata key")
    return MappingProxyType(detached)


def _digest(value: Any) -> str:
    return sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class OrchestrRecord:
    name: str
    state: OrchestrState = OrchestrState.NEW
    payload: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    authority: Authority = Authority.WORKER
    parent: str | None = None
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.name, "task name")
        if not isinstance(self.state, OrchestrState):
            raise ValueError("invalid orchestration state")
        if not isinstance(self.authority, Authority):
            raise ValueError("invalid authority")
        if self.parent is not None:
            _text(self.parent, "parent")
            if self.parent == self.name:
                raise ValueError("task cannot parent itself")
        if not isinstance(self.dependencies, tuple) or len(self.dependencies) > MAX_DEPENDENCIES:
            raise ValueError("invalid dependencies")
        deps = tuple(_text(dep, "dependency") for dep in self.dependencies)
        if self.name in deps or len(set(deps)) != len(deps):
            raise ValueError("invalid dependency set")
        if not isinstance(self.evidence, tuple) or len(self.evidence) > MAX_EVIDENCE:
            raise ValueError("invalid evidence")
        evidence = tuple(_text(item, "evidence") for item in self.evidence)
        object.__setattr__(self, "payload", _freeze_mapping(self.payload))
        object.__setattr__(self, "dependencies", deps)
        object.__setattr__(self, "evidence", evidence)

    @property
    def digest(self) -> str:
        return _digest(
            {
                "authority": self.authority.value,
                "dependencies": self.dependencies,
                "evidence": self.evidence,
                "name": self.name,
                "parent": self.parent,
                "payload": dict(self.payload),
                "state": self.state.value,
                "v": 1,
            }
        )


@dataclass(frozen=True)
class OrchestrLedger:
    records: tuple[OrchestrRecord, ...] = ()

    def __post_init__(self) -> None:
        _validate_graph(self.records)

    def append(self, record: OrchestrRecord) -> "OrchestrLedger":
        if not isinstance(record, OrchestrRecord):
            raise ValueError("invalid record")
        return OrchestrLedger(self.records + (record,))

    @property
    def digest(self) -> str:
        return _digest({"records": [record.digest for record in self.records], "v": 1})


def _validate_graph(records: Sequence[OrchestrRecord]) -> None:
    if len(records) > MAX_TASKS:
        raise ValueError("too many tasks")
    by_name: dict[str, OrchestrRecord] = {}
    for record in records:
        if not isinstance(record, OrchestrRecord):
            raise ValueError("invalid record")
        if record.name in by_name:
            raise ValueError("duplicate record")
        by_name[record.name] = record

    for record in records:
        if record.parent is not None:
            parent = by_name.get(record.parent)
            if parent is None:
                raise ValueError("missing parent")
            if record.authority not in _ALLOWED_DELEGATION[parent.authority]:
                raise ValueError("authority escalation")
        for dep in record.dependencies:
            if dep not in by_name:
                raise ValueError("missing dependency")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        if name in visiting:
            raise ValueError("orchestration cycle")
        visiting.add(name)
        record = by_name[name]
        edges = list(record.dependencies)
        if record.parent is not None:
            edges.append(record.parent)
        for edge in edges:
            visit(edge)
        visiting.remove(name)
        visited.add(name)

    for name in by_name:
        visit(name)


def validate_orchestr(records: Sequence[OrchestrRecord]) -> tuple[str, ...]:
    if isinstance(records, (str, bytes)):
        raise ValueError("records must be a sequence")
    materialized = tuple(records)
    _validate_graph(materialized)
    return tuple(record.digest for record in materialized)
