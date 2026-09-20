"""Durable fingerprint-bound work queue for autonomous repository stewardship."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping

from .growth import growth_recommendations
from .model import RepositoryModel
from .reorganize import propose_reorganization
from .config import MachineConfig
from .workgraph import build_work_graph

MAX_ITEMS = 4096
MAX_STATE_BYTES = 8 * 1024 * 1024
_ALLOWED_STATUS = {"ready", "leased", "completed", "blocked", "stale"}


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class QueueItem:
    identity: str
    source: str
    lane: str
    zone: str
    priority: int
    objective: str
    conflict_keys: tuple[str, ...]
    repository_fingerprint: str
    status: str = "ready"
    attempts: int = 0
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in _ALLOWED_STATUS:
            raise ValueError("invalid queue status")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("priority must be integer")
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int) or self.attempts < 0:
            raise ValueError("attempts must be non-negative")

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "source": self.source,
            "lane": self.lane,
            "zone": self.zone,
            "priority": self.priority,
            "objective": self.objective,
            "conflict_keys": list(self.conflict_keys),
            "repository_fingerprint": self.repository_fingerprint,
            "status": self.status,
            "attempts": self.attempts,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "QueueItem":
        return cls(
            identity=str(value.get("identity", "")),
            source=str(value.get("source", "")),
            lane=str(value.get("lane", "")),
            zone=str(value.get("zone", "")),
            priority=int(value.get("priority", 0)),
            objective=str(value.get("objective", "")),
            conflict_keys=tuple(value.get("conflict_keys", ())),
            repository_fingerprint=str(value.get("repository_fingerprint", "")),
            status=str(value.get("status", "ready")),
            attempts=int(value.get("attempts", 0)),
            evidence=tuple(value.get("evidence", ())),
        )


@dataclass(slots=True)
class MachineWorkQueue:
    sequence: int = 0
    items: dict[str, QueueItem] = field(default_factory=dict)

    def refresh(
        self,
        model: RepositoryModel,
        config: MachineConfig,
    ) -> tuple[str, ...]:
        changed: list[str] = []
        current = model.fingerprint
        for identity, item in list(self.items.items()):
            if item.repository_fingerprint != current and item.status in {"ready", "blocked"}:
                self.items[identity] = replace(item, status="stale")
                changed.append(identity)

        candidates: list[QueueItem] = []
        for node in build_work_graph(model, limit=256).nodes:
            candidates.append(QueueItem(
                identity=node.identity,
                source="finding",
                lane=node.lane,
                zone=node.zone,
                priority=node.priority,
                objective=node.objective,
                conflict_keys=node.conflict_keys,
                repository_fingerprint=current,
                evidence=node.evidence,
            ))
        for recommendation in growth_recommendations(model, limit=64):
            identity = f"growth:{recommendation.code}:{recommendation.zone}"
            candidates.append(QueueItem(
                identity=identity,
                source="growth",
                lane="architecture",
                zone=recommendation.zone,
                priority=recommendation.priority,
                objective=recommendation.objective,
                conflict_keys=(f"zone:{recommendation.zone}", "lane:architecture"),
                repository_fingerprint=current,
                evidence=(recommendation.rationale,),
            ))
        for proposal in propose_reorganization(model, config, limit=64):
            candidates.append(QueueItem(
                identity=f"reorg:{proposal.identity}",
                source="reorganization",
                lane="organization",
                zone=proposal.zone,
                priority=proposal.priority,
                objective=proposal.objective,
                conflict_keys=(f"zone:{proposal.zone}", "lane:organization"),
                repository_fingerprint=current,
                evidence=proposal.paths,
            ))

        for item in candidates:
            existing = self.items.get(item.identity)
            if existing is not None and existing.status == "completed":
                continue
            if existing is None or existing.repository_fingerprint != current:
                if len(self.items) >= MAX_ITEMS:
                    raise RuntimeError("machine work queue capacity exceeded")
                self.items[item.identity] = item
                changed.append(item.identity)

        if changed:
            self.sequence += 1
        return tuple(sorted(set(changed)))

    def ready(
        self,
        *,
        active_conflicts: Iterable[str] = (),
        limit: int = 8,
    ) -> tuple[QueueItem, ...]:
        conflicts = set(active_conflicts)
        selected: list[QueueItem] = []
        values = sorted(
            (item for item in self.items.values() if item.status == "ready"),
            key=lambda item: (-item.priority, item.zone, item.identity),
        )
        for item in values:
            if conflicts.intersection(item.conflict_keys):
                continue
            selected.append(item)
            conflicts.update(item.conflict_keys)
            if len(selected) >= limit:
                break
        return tuple(selected)

    def mark(self, identity: str, status: str) -> QueueItem:
        if status not in _ALLOWED_STATUS:
            raise ValueError("invalid queue status")
        item = self.items[identity]
        updated = replace(
            item,
            status=status,
            attempts=item.attempts + int(status == "leased"),
        )
        self.items[identity] = updated
        self.sequence += 1
        return updated

    def compact(self) -> int:
        stale = [
            identity for identity, item in self.items.items()
            if item.status in {"completed", "stale"}
        ]
        if len(stale) <= MAX_ITEMS // 4:
            return 0
        remove_count = len(stale) - MAX_ITEMS // 4
        for identity in sorted(stale)[:remove_count]:
            self.items.pop(identity, None)
        if remove_count:
            self.sequence += 1
        return remove_count

    def as_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "sequence": self.sequence,
            "items": [
                self.items[key].as_dict()
                for key in sorted(self.items)
            ],
        }

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        state = self.as_dict()
        envelope = {"checksum": _digest(state), "state": state}
        rendered = _canonical(envelope) + "\n"
        if len(rendered.encode("utf-8")) > MAX_STATE_BYTES:
            raise RuntimeError("machine work queue exceeds byte budget")
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
            text=True,
        )
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, destination)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: str | Path) -> "MachineWorkQueue":
        raw = Path(path).read_bytes()
        if len(raw) > MAX_STATE_BYTES:
            raise RuntimeError("machine work queue exceeds byte budget")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("state"), dict):
            raise ValueError("invalid work queue envelope")
        state = payload["state"]
        if payload.get("checksum") != _digest(state):
            raise ValueError("work queue checksum mismatch")
        if state.get("version") != 1 or not isinstance(state.get("items"), list):
            raise ValueError("unsupported work queue format")
        queue = cls(sequence=int(state.get("sequence", 0)))
        for value in state["items"]:
            if not isinstance(value, dict):
                raise ValueError("invalid work queue item")
            item = QueueItem.from_dict(value)
            if item.identity in queue.items:
                raise ValueError("duplicate work queue identity")
            queue.items[item.identity] = item
        return queue
