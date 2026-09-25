"""Memory reconciliation, quality scoring, and deletion propagation.

This module implements the masterplan's memory quality/GC control without
granting it hidden authority. Scoring is deterministic and produces an explicit
decision. Deletion is represented by a tombstone that remains incomplete until
every declared derived projection acknowledges removal.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from threading import RLock
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

STATE_VERSION = 1


def _finite(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _nonnegative_int(name: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


class MemoryAction(str, Enum):
    RETAIN = "retain"
    REVIEW = "review"
    TOMBSTONE = "tombstone"


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    record_id: str
    memory_class: str
    created_at: float
    updated_at: float
    last_accessed_at: float
    confidence: float
    importance: float
    access_count: int = 0
    provenance_count: int = 0
    contradiction_count: int = 0
    derived_targets: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id:
            raise ValueError("record_id must be a non-empty string")
        if not isinstance(self.memory_class, str) or not self.memory_class:
            raise ValueError("memory_class must be a non-empty string")
        created = _finite("created_at", self.created_at)
        updated = _finite("updated_at", self.updated_at)
        accessed = _finite("last_accessed_at", self.last_accessed_at)
        if updated < created:
            raise ValueError("updated_at cannot precede created_at")
        if accessed < created:
            raise ValueError("last_accessed_at cannot precede created_at")
        confidence = _finite("confidence", self.confidence)
        importance = _finite("importance", self.importance)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        if not 0.0 <= importance <= 1.0:
            raise ValueError("importance must be in [0, 1]")
        _nonnegative_int("access_count", self.access_count)
        _nonnegative_int("provenance_count", self.provenance_count)
        _nonnegative_int("contradiction_count", self.contradiction_count)
        if any(
            not isinstance(target, str) or not target
            for target in self.derived_targets
        ):
            raise ValueError("derived_targets must contain non-empty strings")
        if len(set(self.derived_targets)) != len(self.derived_targets):
            raise ValueError("derived_targets must be unique")


@dataclass(frozen=True, slots=True)
class MemoryQualityPolicy:
    half_life_s: float = 30.0 * 24.0 * 3600.0
    retain_threshold: float = 0.45
    tombstone_threshold: float = 0.20
    hard_contradiction_limit: int = 4

    def __post_init__(self) -> None:
        half_life = _finite("half_life_s", self.half_life_s)
        retain = _finite("retain_threshold", self.retain_threshold)
        tombstone = _finite("tombstone_threshold", self.tombstone_threshold)
        if half_life <= 0:
            raise ValueError("half_life_s must be positive")
        if not 0.0 <= tombstone < retain <= 1.0:
            raise ValueError(
                "thresholds must satisfy 0 <= tombstone < retain <= 1"
            )
        if (
            isinstance(self.hard_contradiction_limit, bool)
            or not isinstance(self.hard_contradiction_limit, int)
            or self.hard_contradiction_limit < 1
        ):
            raise ValueError("hard_contradiction_limit must be a positive integer")


@dataclass(frozen=True, slots=True)
class MemoryDecision:
    record_id: str
    action: MemoryAction
    score: float
    reasons: Tuple[str, ...]
    signals: Tuple[Tuple[str, float], ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "action": self.action.value,
            "score": self.score,
            "reasons": list(self.reasons),
            "signals": dict(self.signals),
        }


class MemoryReconciler:
    """Deterministic memory quality/GC policy."""

    def __init__(self, policy: Optional[MemoryQualityPolicy] = None) -> None:
        self.policy = policy or MemoryQualityPolicy()

    def evaluate(self, record: MemoryRecord, *, now: float) -> MemoryDecision:
        if not isinstance(record, MemoryRecord):
            raise TypeError("record must be MemoryRecord")
        resolved_now = _finite("now", now)
        if resolved_now < record.created_at:
            raise ValueError("now cannot precede record creation")

        age_since_use = max(0.0, resolved_now - record.last_accessed_at)
        freshness = math.pow(0.5, age_since_use / self.policy.half_life_s)
        utility = 1.0 - math.exp(-record.access_count / 4.0)
        evidence = 1.0 - math.exp(-record.provenance_count / 2.0)
        contradiction = min(1.0, record.contradiction_count / 4.0)

        score = (
            0.25 * record.confidence
            + 0.25 * record.importance
            + 0.20 * freshness
            + 0.15 * utility
            + 0.15 * evidence
            - 0.35 * contradiction
        )
        score = round(min(1.0, max(0.0, score)), 6)

        reasons = []
        if freshness < 0.25:
            reasons.append("stale")
        if record.confidence < 0.4:
            reasons.append("low-confidence")
        if record.provenance_count == 0:
            reasons.append("unprovenanced")
        if record.contradiction_count:
            reasons.append("contradicted")
        if record.access_count == 0:
            reasons.append("unused")

        if record.contradiction_count >= self.policy.hard_contradiction_limit:
            action = MemoryAction.TOMBSTONE
            reasons.append("hard-contradiction-limit")
        elif score < self.policy.tombstone_threshold:
            action = MemoryAction.TOMBSTONE
            reasons.append("quality-below-tombstone-threshold")
        elif score < self.policy.retain_threshold:
            action = MemoryAction.REVIEW
            reasons.append("quality-requires-review")
        else:
            action = MemoryAction.RETAIN

        signals = (
            ("freshness", round(freshness, 6)),
            ("utility", round(utility, 6)),
            ("evidence", round(evidence, 6)),
            ("contradiction", round(contradiction, 6)),
        )
        return MemoryDecision(
            record_id=record.record_id,
            action=action,
            score=score,
            reasons=tuple(dict.fromkeys(reasons)),
            signals=signals,
        )

    def evaluate_many(
        self,
        records: Iterable[MemoryRecord],
        *,
        now: float,
    ) -> Tuple[MemoryDecision, ...]:
        resolved = sorted(tuple(records), key=lambda record: record.record_id)
        if len({record.record_id for record in resolved}) != len(resolved):
            raise ValueError("memory record ids must be unique")
        return tuple(self.evaluate(record, now=now) for record in resolved)


@dataclass(frozen=True, slots=True)
class MemoryTombstone:
    tombstone_id: str
    record_id: str
    issued_at: float
    reason: str
    targets: Tuple[str, ...]
    acknowledged: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.tombstone_id or not self.record_id or not self.reason:
            raise ValueError(
                "tombstone_id, record_id, and reason must be non-empty"
            )
        _finite("issued_at", self.issued_at)
        if not self.targets:
            raise ValueError("tombstone must contain at least one target")
        if any(not isinstance(target, str) or not target for target in self.targets):
            raise ValueError("tombstone targets must be non-empty strings")
        if len(set(self.targets)) != len(self.targets):
            raise ValueError("tombstone targets must be unique")
        if not set(self.acknowledged).issubset(set(self.targets)):
            raise ValueError("acknowledgements must reference tombstone targets")

    @property
    def pending(self) -> Tuple[str, ...]:
        acknowledged = set(self.acknowledged)
        return tuple(target for target in self.targets if target not in acknowledged)

    @property
    def complete(self) -> bool:
        return not self.pending

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tombstone_id": self.tombstone_id,
            "record_id": self.record_id,
            "issued_at": self.issued_at,
            "reason": self.reason,
            "targets": list(self.targets),
            "acknowledged": list(self.acknowledged),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MemoryTombstone":
        if not isinstance(payload, Mapping):
            raise ValueError("tombstone payload must be a mapping")
        targets = payload.get("targets")
        acknowledged = payload.get("acknowledged")
        if not isinstance(targets, list) or not isinstance(acknowledged, list):
            raise ValueError("tombstone targets/acknowledged must be lists")
        return cls(
            tombstone_id=str(payload.get("tombstone_id") or ""),
            record_id=str(payload.get("record_id") or ""),
            issued_at=_finite("issued_at", payload.get("issued_at")),
            reason=str(payload.get("reason") or ""),
            targets=tuple(str(target) for target in targets),
            acknowledged=tuple(str(target) for target in acknowledged),
        )


class TombstoneLedger:
    """Durable deletion propagation ledger with explicit completion fencing."""

    def __init__(self) -> None:
        self._entries: Dict[str, MemoryTombstone] = {}
        self._by_record: Dict[str, str] = {}
        self._lock = RLock()

    @staticmethod
    def _tombstone_id(
        record_id: str,
        issued_at: float,
        reason: str,
        targets: Tuple[str, ...],
    ) -> str:
        encoded = json.dumps(
            {
                "record_id": record_id,
                "issued_at": issued_at,
                "reason": reason,
                "targets": targets,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.blake2b(encoded, digest_size=16).hexdigest()

    def issue(
        self,
        record: MemoryRecord,
        *,
        issued_at: float,
        reason: str,
    ) -> MemoryTombstone:
        if not isinstance(record, MemoryRecord):
            raise TypeError("record must be MemoryRecord")
        if not isinstance(reason, str) or not reason:
            raise ValueError("reason must be a non-empty string")
        timestamp = _finite("issued_at", issued_at)
        targets = tuple(
            dict.fromkeys(
                (f"memory:{record.record_id}",) + tuple(record.derived_targets)
            )
        )
        tombstone = MemoryTombstone(
            tombstone_id=self._tombstone_id(
                record.record_id,
                timestamp,
                reason,
                targets,
            ),
            record_id=record.record_id,
            issued_at=timestamp,
            reason=reason,
            targets=targets,
        )
        with self._lock:
            existing_id = self._by_record.get(record.record_id)
            if existing_id is not None:
                return self._entries[existing_id]
            self._entries[tombstone.tombstone_id] = tombstone
            self._by_record[record.record_id] = tombstone.tombstone_id
        return tombstone

    def acknowledge(
        self,
        tombstone_id: str,
        target: str,
    ) -> MemoryTombstone:
        with self._lock:
            current = self._entries.get(tombstone_id)
            if current is None:
                raise KeyError("unknown memory tombstone")
            if target not in current.targets:
                raise ValueError("target is not part of tombstone propagation set")
            acknowledged = tuple(
                target_name
                for target_name in current.targets
                if target_name in set(current.acknowledged) | {target}
            )
            updated = MemoryTombstone(
                tombstone_id=current.tombstone_id,
                record_id=current.record_id,
                issued_at=current.issued_at,
                reason=current.reason,
                targets=current.targets,
                acknowledged=acknowledged,
            )
            self._entries[tombstone_id] = updated
            return updated

    def get(self, tombstone_id: str) -> Optional[MemoryTombstone]:
        with self._lock:
            return self._entries.get(tombstone_id)

    def for_record(self, record_id: str) -> Optional[MemoryTombstone]:
        with self._lock:
            tombstone_id = self._by_record.get(record_id)
            return (
                None
                if tombstone_id is None
                else self._entries.get(tombstone_id)
            )

    def incomplete(self) -> Tuple[MemoryTombstone, ...]:
        with self._lock:
            return tuple(
                tombstone
                for _, tombstone in sorted(self._entries.items())
                if not tombstone.complete
            )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": STATE_VERSION,
                "tombstones": [
                    tombstone.to_dict()
                    for _, tombstone in sorted(self._entries.items())
                ],
            }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> "TombstoneLedger":
        if not isinstance(payload, Mapping) or payload.get("version") != STATE_VERSION:
            raise ValueError("unsupported tombstone ledger state")
        rows = payload.get("tombstones")
        if not isinstance(rows, list):
            raise ValueError("tombstone ledger rows must be a list")
        ledger = cls()
        for row in rows:
            tombstone = MemoryTombstone.from_dict(row)
            if tombstone.tombstone_id in ledger._entries:
                raise ValueError("duplicate tombstone id")
            if tombstone.record_id in ledger._by_record:
                raise ValueError("duplicate active tombstone for record")
            ledger._entries[tombstone.tombstone_id] = tombstone
            ledger._by_record[tombstone.record_id] = tombstone.tombstone_id
        return ledger
