"""Adapters from Internal Systems' swarm directory into the agent edge registry.

The edge never imports swarm internals at module import time and never
writes back into them: it *reads* a directory snapshot through a small
:class:`SwarmDirectory` protocol and projects it into
:class:`~skeleton.gate_plane.agent_edge.routing.AgentEndpoint` rows.
Internal Systems owns the swarm; this module only adapts its shape.

Accepted snapshot shapes (first match wins per row)::

    {"agents": [{"id"|"agent_id": ..., "lane"|"role": ..., "capabilities": [...],
                 "capacity"?: int, "weight"?: int, "enabled"?: bool, "draining"?: bool}]}
    {"<agent_id>": {"lane": ..., "capabilities": [...]}, ...}

Rows that fail validation are skipped and reported, never fatal, so one
malformed swarm entry cannot take routing down.
"""

from __future__ import annotations

import importlib
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Protocol, Tuple

from skeleton.gate_plane.agent_edge.envelope import EnvelopeError
from skeleton.gate_plane.agent_edge.routing import AgentEndpoint, AgentRegistry, RoutingError

DEFAULT_SWARM_MODULE = "skeleton.swarm.capabilities"
DEFAULT_SWARM_FUNCTION = "capabilities"
_SANITISE = re.compile(r"[^a-z0-9_.-]+")


class SwarmDirectory(Protocol):
    def snapshot(self) -> Mapping[str, Any]:
        ...


@dataclass
class StaticSwarmDirectory:
    """Fixed snapshot (tests, local dev, chaos)."""

    data: Mapping[str, Any] = field(default_factory=dict)

    def snapshot(self) -> Mapping[str, Any]:
        return self.data


@dataclass
class CallableSwarmDirectory:
    fn: Callable[[], Mapping[str, Any]]

    def snapshot(self) -> Mapping[str, Any]:
        out = self.fn()
        if not isinstance(out, Mapping):
            raise TypeError("swarm directory callable must return a mapping")
        return out


@dataclass
class ModuleSwarmDirectory:
    """Lazily resolves ``module:function`` (default: Internal Systems' capabilities())."""

    module: str = DEFAULT_SWARM_MODULE
    function: str = DEFAULT_SWARM_FUNCTION

    def snapshot(self) -> Mapping[str, Any]:
        mod = importlib.import_module(self.module)
        fn = getattr(mod, self.function)
        out = fn()
        if not isinstance(out, Mapping):
            raise TypeError(f"{self.module}.{self.function}() did not return a mapping")
        return out


def _agent_id(raw: Any) -> str:
    text = _SANITISE.sub("-", str(raw).strip().lower()).strip("-.")
    if not text or not text[0].isalpha():
        text = f"a-{text}"
    return text[:63]


def _capability(raw: Any) -> str:
    text = re.sub(r"[^a-z0-9_.*-]+", "_", str(raw).strip().lower()).strip("._")
    return text


def _rows(snapshot: Mapping[str, Any]) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    agents = snapshot.get("agents") if isinstance(snapshot, Mapping) else None
    if isinstance(agents, list):
        for i, row in enumerate(agents):
            if isinstance(row, Mapping):
                yield str(row.get("agent_id") or row.get("id") or f"#{i}"), row
        return
    for key, row in snapshot.items():
        if isinstance(row, Mapping) and ("capabilities" in row or "lane" in row or "role" in row):
            yield str(key), row


@dataclass(frozen=True)
class SyncReport:
    added: Tuple[str, ...]
    updated: Tuple[str, ...]
    removed: Tuple[str, ...]
    skipped: Mapping[str, str]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "added": list(self.added),
            "updated": list(self.updated),
            "removed": list(self.removed),
            "skipped": dict(self.skipped),
            "error": self.error,
        }


def project(snapshot: Mapping[str, Any], *, default_lane: str = "swarm", default_capacity: int = 8) -> Tuple[List[AgentEndpoint], Dict[str, str]]:
    endpoints: List[AgentEndpoint] = []
    skipped: Dict[str, str] = {}
    for key, row in _rows(snapshot):
        try:
            agent_id = _agent_id(row.get("agent_id") or row.get("id") or key)
            lane = _agent_id(row.get("lane") or row.get("role") or default_lane)[:32].replace(".", "-")
            caps_raw = row.get("capabilities") or ()
            if isinstance(caps_raw, Mapping):
                caps_raw = [k for k, v in caps_raw.items() if v]
            caps = frozenset(c for c in (_capability(x) for x in caps_raw) if c)
            endpoints.append(
                AgentEndpoint(
                    agent_id=agent_id,
                    lane=lane,
                    capabilities=caps,
                    capacity=int(row.get("capacity", default_capacity)),
                    weight=int(row.get("weight", 100)),
                    enabled=bool(row.get("enabled", True)),
                    draining=bool(row.get("draining", False)),
                    labels={"source": "swarm"},
                )
            )
        except (RoutingError, EnvelopeError, TypeError, ValueError) as exc:
            skipped[key] = str(exc)[:200]
    return endpoints, skipped


class SwarmRegistryAdapter:
    """Keeps an :class:`AgentRegistry` in sync with a swarm directory.

    Only endpoints this adapter created (label ``source=swarm``) are removed
    when they disappear from the swarm; manually registered agents are left
    alone.
    """

    def __init__(self, directory: SwarmDirectory, registry: AgentRegistry, *, default_lane: str = "swarm") -> None:
        self.directory = directory
        self.registry = registry
        self.default_lane = default_lane
        self.last_report: Optional[SyncReport] = None

    def sync(self) -> SyncReport:
        try:
            snap = self.directory.snapshot()
        except Exception as exc:  # noqa: BLE001 - swarm outage keeps the last good registry
            report = SyncReport((), (), (), {}, error=f"{type(exc).__name__}: {exc}"[:300])
            self.last_report = report
            return report
        endpoints, skipped = project(snap, default_lane=self.default_lane)
        seen = set()
        added: List[str] = []
        updated: List[str] = []
        for ep in endpoints:
            seen.add(ep.agent_id)
            existing = self.registry.get(ep.agent_id)
            if existing is None:
                added.append(ep.agent_id)
                self.registry.upsert(ep)
            elif existing != ep:
                if existing.labels.get("source") != "swarm":
                    skipped[ep.agent_id] = "manually registered; not overwritten"
                    continue
                updated.append(ep.agent_id)
                self.registry.upsert(ep)
        removed = []
        for ep in self.registry.all():
            if ep.labels.get("source") == "swarm" and ep.agent_id not in seen:
                self.registry.remove(ep.agent_id)
                removed.append(ep.agent_id)
        report = SyncReport(tuple(added), tuple(updated), tuple(removed), skipped)
        self.last_report = report
        return report


__all__ = [
    "CallableSwarmDirectory",
    "DEFAULT_SWARM_FUNCTION",
    "DEFAULT_SWARM_MODULE",
    "ModuleSwarmDirectory",
    "StaticSwarmDirectory",
    "SwarmDirectory",
    "SwarmRegistryAdapter",
    "SyncReport",
    "project",
]
