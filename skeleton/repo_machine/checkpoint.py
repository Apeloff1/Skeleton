"""Durable steward checkpoints for fairness, recovery and stale-work detection."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping

MAX_COMPLETED = 4096
MAX_FAILED = 1024
MAX_BYTES = 4 * 1024 * 1024


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ObjectiveOutcome:
    identity: str
    lane: str
    completed_at: int
    repository_fingerprint: str
    status: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in {"completed", "failed", "blocked", "abandoned"}:
            raise ValueError("invalid objective outcome status")
        if isinstance(self.completed_at, bool) or not isinstance(self.completed_at, int) or self.completed_at <= 0:
            raise ValueError("completed_at must be positive")

    def as_dict(self) -> dict[str, object]:
        return {
            "identity": self.identity,
            "lane": self.lane,
            "completed_at": self.completed_at,
            "repository_fingerprint": self.repository_fingerprint,
            "status": self.status,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> "ObjectiveOutcome":
        return cls(
            identity=str(value.get("identity", "")),
            lane=str(value.get("lane", "")),
            completed_at=int(value.get("completed_at", 0)),
            repository_fingerprint=str(value.get("repository_fingerprint", "")),
            status=str(value.get("status", "")),
            evidence=tuple(value.get("evidence", ())),
        )


@dataclass(slots=True)
class StewardCheckpoint:
    sequence: int = 0
    last_repository_fingerprint: str = ""
    lane_streak: str = ""
    lane_streak_count: int = 0
    lane_counts: dict[str, int] = field(default_factory=dict)
    outcomes: list[ObjectiveOutcome] = field(default_factory=list)

    def record(
        self,
        outcome: ObjectiveOutcome,
    ) -> None:
        self.sequence += 1
        self.last_repository_fingerprint = outcome.repository_fingerprint
        self.lane_counts[outcome.lane] = self.lane_counts.get(outcome.lane, 0) + 1
        if self.lane_streak == outcome.lane:
            self.lane_streak_count += 1
        else:
            self.lane_streak = outcome.lane
            self.lane_streak_count = 1
        self.outcomes.append(outcome)
        if len(self.outcomes) > MAX_COMPLETED:
            self.outcomes = self.outcomes[-MAX_COMPLETED:]

    def failures(self) -> tuple[ObjectiveOutcome, ...]:
        return tuple(
            item
            for item in self.outcomes[-MAX_FAILED:]
            if item.status in {"failed", "blocked"}
        )

    def completed_ids(self) -> tuple[str, ...]:
        return tuple(sorted({
            item.identity
            for item in self.outcomes
            if item.status == "completed"
        }))

    def recent_lane_count(self, lane: str, *, window: int = 20) -> int:
        return sum(
            item.lane == lane
            for item in self.outcomes[-window:]
        )

    def fingerprint_stale(self, current_fingerprint: str) -> bool:
        return bool(
            self.last_repository_fingerprint
            and self.last_repository_fingerprint != current_fingerprint
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "version": 1,
            "sequence": self.sequence,
            "last_repository_fingerprint": self.last_repository_fingerprint,
            "lane_streak": self.lane_streak,
            "lane_streak_count": self.lane_streak_count,
            "lane_counts": dict(sorted(self.lane_counts.items())),
            "outcomes": [item.as_dict() for item in self.outcomes],
        }

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        state = self.as_dict()
        envelope = {"checksum": _digest(state), "state": state}
        rendered = _canonical(envelope) + "\n"
        if len(rendered.encode("utf-8")) > MAX_BYTES:
            raise RuntimeError("steward checkpoint exceeds byte budget")
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
    def load(cls, path: str | Path) -> "StewardCheckpoint":
        raw = Path(path).read_bytes()
        if len(raw) > MAX_BYTES:
            raise RuntimeError("steward checkpoint exceeds byte budget")
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("state"), dict):
            raise ValueError("invalid checkpoint envelope")
        state = payload["state"]
        if payload.get("checksum") != _digest(state):
            raise ValueError("checkpoint checksum mismatch")
        if state.get("version") != 1:
            raise ValueError("unsupported checkpoint version")
        outcomes_raw = state.get("outcomes", [])
        if not isinstance(outcomes_raw, list):
            raise ValueError("checkpoint outcomes must be a list")
        outcomes = [
            ObjectiveOutcome.from_dict(item)
            for item in outcomes_raw
            if isinstance(item, dict)
        ]
        lane_counts_raw = state.get("lane_counts", {})
        if not isinstance(lane_counts_raw, dict):
            raise ValueError("checkpoint lane_counts must be an object")
        lane_counts = {
            str(key): int(value)
            for key, value in lane_counts_raw.items()
        }
        return cls(
            sequence=int(state.get("sequence", 0)),
            last_repository_fingerprint=str(state.get("last_repository_fingerprint", "")),
            lane_streak=str(state.get("lane_streak", "")),
            lane_streak_count=int(state.get("lane_streak_count", 0)),
            lane_counts=lane_counts,
            outcomes=outcomes,
        )
