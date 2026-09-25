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



class MemoryConflictResolution(str, Enum):
    UNRESOLVED = "unresolved"
    SUPERSEDE = "supersede"
    KEEP_BOTH = "keep-both"


@dataclass(frozen=True, slots=True)
class MemoryConflictCandidate:
    """One exact-scope candidate participating in a memory contradiction."""

    record_id: str
    scope_key: str
    claim_key: str
    payload_digest: str
    confidence: float
    provenance_count: int
    updated_at: float

    def __post_init__(self) -> None:
        for field, value in (
            ("record_id", self.record_id),
            ("scope_key", self.scope_key),
            ("claim_key", self.claim_key),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field} must be a non-empty string")
        if (
            not isinstance(self.payload_digest, str)
            or len(self.payload_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in self.payload_digest)
        ):
            raise ValueError("payload_digest must be lowercase sha256")
        confidence = _finite("confidence", self.confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be in [0, 1]")
        _nonnegative_int("provenance_count", self.provenance_count)
        _finite("updated_at", self.updated_at)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "scope_key": self.scope_key,
            "claim_key": self.claim_key,
            "payload_digest": self.payload_digest,
            "confidence": self.confidence,
            "provenance_count": self.provenance_count,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MemoryConflictCandidate":
        if not isinstance(payload, Mapping):
            raise ValueError("conflict candidate must be a mapping")
        return cls(
            record_id=str(payload.get("record_id") or ""),
            scope_key=str(payload.get("scope_key") or ""),
            claim_key=str(payload.get("claim_key") or ""),
            payload_digest=str(payload.get("payload_digest") or ""),
            confidence=_finite("confidence", payload.get("confidence")),
            provenance_count=_nonnegative_int(
                "provenance_count",
                payload.get("provenance_count"),
            ),
            updated_at=_finite("updated_at", payload.get("updated_at")),
        )


@dataclass(frozen=True, slots=True)
class MemoryConflictSet:
    """Explicit unresolved/resolved contradiction among exact-scope memories."""

    conflict_id: str
    scope_key: str
    claim_key: str
    candidates: Tuple[MemoryConflictCandidate, ...]
    created_at: float
    resolution: MemoryConflictResolution = MemoryConflictResolution.UNRESOLVED
    winner_id: Optional[str] = None
    superseded_ids: Tuple[str, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.conflict_id, str) or not self.conflict_id:
            raise ValueError("conflict_id must be a non-empty string")
        if not isinstance(self.scope_key, str) or not self.scope_key:
            raise ValueError("scope_key must be a non-empty string")
        if not isinstance(self.claim_key, str) or not self.claim_key:
            raise ValueError("claim_key must be a non-empty string")
        _finite("created_at", self.created_at)
        if len(self.candidates) < 2:
            raise ValueError("conflict set requires at least two candidates")
        ids = tuple(candidate.record_id for candidate in self.candidates)
        if len(set(ids)) != len(ids):
            raise ValueError("conflict candidate ids must be unique")
        if any(candidate.scope_key != self.scope_key for candidate in self.candidates):
            raise ValueError("conflict candidates cannot cross memory scopes")
        if any(candidate.claim_key != self.claim_key for candidate in self.candidates):
            raise ValueError("conflict candidates must describe the same claim")
        if len({candidate.payload_digest for candidate in self.candidates}) < 2:
            raise ValueError("conflict set requires divergent payload digests")
        try:
            resolution = MemoryConflictResolution(self.resolution)
        except ValueError as exc:
            raise ValueError("conflict resolution is invalid") from exc
        object.__setattr__(self, "resolution", resolution)
        candidate_ids = set(ids)
        if self.winner_id is not None and self.winner_id not in candidate_ids:
            raise ValueError("winner_id must reference a conflict candidate")
        if any(item not in candidate_ids for item in self.superseded_ids):
            raise ValueError("superseded ids must reference conflict candidates")
        if len(set(self.superseded_ids)) != len(self.superseded_ids):
            raise ValueError("superseded ids must be unique")
        if resolution is MemoryConflictResolution.UNRESOLVED:
            if self.winner_id is not None or self.superseded_ids:
                raise ValueError("unresolved conflict cannot declare a winner")
        elif resolution is MemoryConflictResolution.SUPERSEDE:
            if self.winner_id is None:
                raise ValueError("supersede resolution requires winner_id")
            expected = candidate_ids - {self.winner_id}
            if set(self.superseded_ids) != expected:
                raise ValueError("supersede resolution must supersede every loser")
        elif resolution is MemoryConflictResolution.KEEP_BOTH:
            if self.winner_id is not None or self.superseded_ids:
                raise ValueError("keep-both resolution cannot supersede candidates")
        if resolution is not MemoryConflictResolution.UNRESOLVED and not self.reason:
            raise ValueError("resolved conflict requires a reason")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conflict_id": self.conflict_id,
            "scope_key": self.scope_key,
            "claim_key": self.claim_key,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "created_at": self.created_at,
            "resolution": self.resolution.value,
            "winner_id": self.winner_id,
            "superseded_ids": list(self.superseded_ids),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "MemoryConflictSet":
        if not isinstance(payload, Mapping):
            raise ValueError("conflict set must be a mapping")
        raw_candidates = payload.get("candidates")
        raw_superseded = payload.get("superseded_ids")
        if not isinstance(raw_candidates, list):
            raise ValueError("conflict candidates must be a list")
        if not isinstance(raw_superseded, list):
            raise ValueError("superseded_ids must be a list")
        return cls(
            conflict_id=str(payload.get("conflict_id") or ""),
            scope_key=str(payload.get("scope_key") or ""),
            claim_key=str(payload.get("claim_key") or ""),
            candidates=tuple(
                MemoryConflictCandidate.from_dict(item)
                for item in raw_candidates
            ),
            created_at=_finite("created_at", payload.get("created_at")),
            resolution=MemoryConflictResolution(
                str(payload.get("resolution") or "unresolved")
            ),
            winner_id=(
                None
                if payload.get("winner_id") is None
                else str(payload.get("winner_id"))
            ),
            superseded_ids=tuple(str(item) for item in raw_superseded),
            reason=str(payload.get("reason") or ""),
        )


@dataclass(frozen=True, slots=True)
class MemoryReconciliationPolicy:
    """Conservative automatic conflict-resolution thresholds."""

    min_confidence_margin: float = 0.20
    min_provenance_margin: int = 1
    require_winner_provenance: bool = True

    def __post_init__(self) -> None:
        margin = _finite("min_confidence_margin", self.min_confidence_margin)
        if not 0.0 <= margin <= 1.0:
            raise ValueError("min_confidence_margin must be in [0, 1]")
        _nonnegative_int("min_provenance_margin", self.min_provenance_margin)
        if not isinstance(self.require_winner_provenance, bool):
            raise ValueError("require_winner_provenance must be boolean")


class MemoryConflictResolver:
    """Build and conservatively resolve same-scope contradiction sets."""

    def __init__(
        self,
        policy: Optional[MemoryReconciliationPolicy] = None,
    ) -> None:
        self.policy = policy or MemoryReconciliationPolicy()

    @staticmethod
    def _conflict_id(
        scope_key: str,
        claim_key: str,
        candidates: Tuple[MemoryConflictCandidate, ...],
    ) -> str:
        encoded = json.dumps(
            {
                "scope_key": scope_key,
                "claim_key": claim_key,
                "candidates": [
                    (candidate.record_id, candidate.payload_digest)
                    for candidate in candidates
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.blake2b(encoded, digest_size=16).hexdigest()

    def build(
        self,
        candidates: Iterable[MemoryConflictCandidate],
        *,
        created_at: float,
    ) -> MemoryConflictSet:
        resolved = tuple(sorted(tuple(candidates), key=lambda row: row.record_id))
        if len(resolved) < 2:
            raise ValueError("conflict set requires at least two candidates")
        scope = resolved[0].scope_key
        claim = resolved[0].claim_key
        if any(candidate.scope_key != scope for candidate in resolved):
            raise ValueError("conflict candidates cannot cross memory scopes")
        if any(candidate.claim_key != claim for candidate in resolved):
            raise ValueError("conflict candidates must describe the same claim")
        return MemoryConflictSet(
            conflict_id=self._conflict_id(scope, claim, resolved),
            scope_key=scope,
            claim_key=claim,
            candidates=resolved,
            created_at=_finite("created_at", created_at),
        )

    def resolve(
        self,
        conflict: MemoryConflictSet,
        *,
        quality_actions: Optional[Mapping[str, MemoryAction]] = None,
    ) -> MemoryConflictSet:
        if not isinstance(conflict, MemoryConflictSet):
            raise TypeError("conflict must be MemoryConflictSet")
        if conflict.resolution is not MemoryConflictResolution.UNRESOLVED:
            return conflict

        actions: Dict[str, MemoryAction] = {}
        if quality_actions is not None:
            for record_id, raw_action in quality_actions.items():
                if record_id not in {row.record_id for row in conflict.candidates}:
                    raise ValueError("quality action references non-candidate memory")
                actions[record_id] = MemoryAction(raw_action)

        ranked = sorted(
            conflict.candidates,
            key=lambda row: (
                row.confidence,
                row.provenance_count,
                row.updated_at,
                row.record_id,
            ),
            reverse=True,
        )
        viable = [
            candidate
            for candidate in ranked
            if actions.get(candidate.record_id) is not MemoryAction.TOMBSTONE
        ]
        if not viable:
            return conflict

        retain = [
            candidate
            for candidate in viable
            if actions.get(candidate.record_id) is MemoryAction.RETAIN
        ]
        review_present = any(
            actions.get(candidate.record_id) is MemoryAction.REVIEW
            for candidate in viable
        )
        if quality_actions is not None and review_present:
            return conflict

        winner: Optional[MemoryConflictCandidate] = None
        reason = ""
        if len(retain) == 1 and all(
            actions.get(candidate.record_id) is MemoryAction.TOMBSTONE
            for candidate in conflict.candidates
            if candidate.record_id != retain[0].record_id
        ):
            winner = retain[0]
            reason = "quality-policy-unique-retain"
        elif len(viable) == 1:
            winner = viable[0]
            reason = "all-alternatives-quality-tombstoned"
        elif len(viable) >= 2:
            first, second = viable[0], viable[1]
            confidence_margin = first.confidence - second.confidence
            provenance_margin = first.provenance_count - second.provenance_count
            enough_provenance = (
                first.provenance_count > 0
                if self.policy.require_winner_provenance
                else True
            )
            if (
                confidence_margin >= self.policy.min_confidence_margin
                and provenance_margin >= self.policy.min_provenance_margin
                and enough_provenance
            ):
                winner = first
                reason = "confidence-and-provenance-dominance"

        if winner is None:
            return conflict
        superseded = tuple(
            candidate.record_id
            for candidate in conflict.candidates
            if candidate.record_id != winner.record_id
        )
        return MemoryConflictSet(
            conflict_id=conflict.conflict_id,
            scope_key=conflict.scope_key,
            claim_key=conflict.claim_key,
            candidates=conflict.candidates,
            created_at=conflict.created_at,
            resolution=MemoryConflictResolution.SUPERSEDE,
            winner_id=winner.record_id,
            superseded_ids=superseded,
            reason=reason,
        )

    def keep_both(
        self,
        conflict: MemoryConflictSet,
        *,
        reason: str,
    ) -> MemoryConflictSet:
        if not isinstance(conflict, MemoryConflictSet):
            raise TypeError("conflict must be MemoryConflictSet")
        normalized = str(reason).strip()
        if not normalized:
            raise ValueError("keep-both resolution requires a reason")
        if conflict.resolution is not MemoryConflictResolution.UNRESOLVED:
            return conflict
        return MemoryConflictSet(
            conflict_id=conflict.conflict_id,
            scope_key=conflict.scope_key,
            claim_key=conflict.claim_key,
            candidates=conflict.candidates,
            created_at=conflict.created_at,
            resolution=MemoryConflictResolution.KEEP_BOTH,
            reason=normalized,
        )


class MemoryConflictLedger:
    """Snapshot-safe conflict ledger; unresolved sets are never silently replaced."""

    def __init__(self) -> None:
        self._entries: Dict[str, MemoryConflictSet] = {}
        self._active_by_claim: Dict[Tuple[str, str], str] = {}
        self._lock = RLock()

    def open(self, conflict: MemoryConflictSet) -> MemoryConflictSet:
        if not isinstance(conflict, MemoryConflictSet):
            raise TypeError("conflict must be MemoryConflictSet")
        key = (conflict.scope_key, conflict.claim_key)
        with self._lock:
            existing_id = self._active_by_claim.get(key)
            if existing_id is not None:
                existing = self._entries[existing_id]
                if existing == conflict:
                    return existing
                if existing.resolution is MemoryConflictResolution.UNRESOLVED:
                    raise ValueError(
                        "cannot replace unresolved conflict set for scope/claim"
                    )
            self._entries[conflict.conflict_id] = conflict
            if conflict.resolution is MemoryConflictResolution.UNRESOLVED:
                self._active_by_claim[key] = conflict.conflict_id
            else:
                self._active_by_claim.pop(key, None)
            return conflict

    def resolve(self, conflict: MemoryConflictSet) -> MemoryConflictSet:
        if not isinstance(conflict, MemoryConflictSet):
            raise TypeError("conflict must be MemoryConflictSet")
        if conflict.resolution is MemoryConflictResolution.UNRESOLVED:
            raise ValueError("resolved conflict must carry a terminal resolution")
        with self._lock:
            current = self._entries.get(conflict.conflict_id)
            if current is None:
                raise KeyError("unknown memory conflict")
            if (
                current.scope_key != conflict.scope_key
                or current.claim_key != conflict.claim_key
                or current.candidates != conflict.candidates
            ):
                raise ValueError("resolved conflict does not match opened conflict")
            if current.resolution is not MemoryConflictResolution.UNRESOLVED:
                if current != conflict:
                    raise ValueError("memory conflict already resolved differently")
                return current
            self._entries[conflict.conflict_id] = conflict
            self._active_by_claim.pop(
                (conflict.scope_key, conflict.claim_key),
                None,
            )
            return conflict

    def get(self, conflict_id: str) -> Optional[MemoryConflictSet]:
        with self._lock:
            return self._entries.get(conflict_id)

    def unresolved(self) -> Tuple[MemoryConflictSet, ...]:
        with self._lock:
            return tuple(
                conflict
                for _, conflict in sorted(self._entries.items())
                if conflict.resolution is MemoryConflictResolution.UNRESOLVED
            )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "version": STATE_VERSION,
                "conflicts": [
                    conflict.to_dict()
                    for _, conflict in sorted(self._entries.items())
                ],
            }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, Any]) -> "MemoryConflictLedger":
        if not isinstance(payload, Mapping) or payload.get("version") != STATE_VERSION:
            raise ValueError("unsupported memory conflict ledger state")
        rows = payload.get("conflicts")
        if not isinstance(rows, list):
            raise ValueError("memory conflict rows must be a list")
        ledger = cls()
        for row in rows:
            conflict = MemoryConflictSet.from_dict(row)
            if conflict.conflict_id in ledger._entries:
                raise ValueError("duplicate memory conflict id")
            key = (conflict.scope_key, conflict.claim_key)
            if (
                conflict.resolution is MemoryConflictResolution.UNRESOLVED
                and key in ledger._active_by_claim
            ):
                raise ValueError("duplicate unresolved conflict for scope/claim")
            ledger._entries[conflict.conflict_id] = conflict
            if conflict.resolution is MemoryConflictResolution.UNRESOLVED:
                ledger._active_by_claim[key] = conflict.conflict_id
        return ledger


class MemoryGCDisposition(str, Enum):
    RETAIN = "retain"
    REVIEW = "review"
    TOMBSTONE = "tombstone"


@dataclass(frozen=True, slots=True)
class MemoryReachability:
    record_id: str
    roots: Tuple[str, ...] = ()
    retention_until: Optional[float] = None
    legal_hold: bool = False
    audit_required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id:
            raise ValueError("record_id must be a non-empty string")
        if any(not isinstance(root, str) or not root for root in self.roots):
            raise ValueError("roots must contain non-empty strings")
        if len(set(self.roots)) != len(self.roots):
            raise ValueError("roots must be unique")
        if self.retention_until is not None:
            _finite("retention_until", self.retention_until)
        if not isinstance(self.legal_hold, bool):
            raise ValueError("legal_hold must be boolean")
        if not isinstance(self.audit_required, bool):
            raise ValueError("audit_required must be boolean")


@dataclass(frozen=True, slots=True)
class MemoryGCEntry:
    record_id: str
    disposition: MemoryGCDisposition
    quality_action: MemoryAction
    reasons: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id:
            raise ValueError("record_id must be a non-empty string")
        object.__setattr__(
            self,
            "disposition",
            MemoryGCDisposition(self.disposition),
        )
        object.__setattr__(
            self,
            "quality_action",
            MemoryAction(self.quality_action),
        )
        if any(not isinstance(reason, str) or not reason for reason in self.reasons):
            raise ValueError("GC reasons must contain non-empty strings")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "disposition": self.disposition.value,
            "quality_action": self.quality_action.value,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class MemoryGCPlan:
    generated_at: float
    entries: Tuple[MemoryGCEntry, ...]

    def __post_init__(self) -> None:
        _finite("generated_at", self.generated_at)
        ids = tuple(entry.record_id for entry in self.entries)
        if len(ids) != len(set(ids)):
            raise ValueError("GC plan record ids must be unique")

    @property
    def retain_ids(self) -> Tuple[str, ...]:
        return tuple(
            entry.record_id
            for entry in self.entries
            if entry.disposition is MemoryGCDisposition.RETAIN
        )

    @property
    def review_ids(self) -> Tuple[str, ...]:
        return tuple(
            entry.record_id
            for entry in self.entries
            if entry.disposition is MemoryGCDisposition.REVIEW
        )

    @property
    def tombstone_ids(self) -> Tuple[str, ...]:
        return tuple(
            entry.record_id
            for entry in self.entries
            if entry.disposition is MemoryGCDisposition.TOMBSTONE
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "entries": [entry.to_dict() for entry in self.entries],
        }


class MemoryGCPlanner:
    """Reachability/retention-aware GC planning; never directly mutates memory."""

    def __init__(self, reconciler: Optional[MemoryReconciler] = None) -> None:
        self.reconciler = reconciler or MemoryReconciler()

    def plan(
        self,
        records: Iterable[MemoryRecord],
        *,
        reachability: Iterable[MemoryReachability] = (),
        now: float,
    ) -> MemoryGCPlan:
        resolved_now = _finite("now", now)
        record_rows = tuple(sorted(tuple(records), key=lambda row: row.record_id))
        if len({row.record_id for row in record_rows}) != len(record_rows):
            raise ValueError("memory record ids must be unique")
        reach_rows = tuple(reachability)
        if len({row.record_id for row in reach_rows}) != len(reach_rows):
            raise ValueError("reachability record ids must be unique")
        known_ids = {row.record_id for row in record_rows}
        if any(row.record_id not in known_ids for row in reach_rows):
            raise ValueError("reachability references unknown memory record")
        reach_by_id = {row.record_id: row for row in reach_rows}

        entries: list[MemoryGCEntry] = []
        for record in record_rows:
            decision = self.reconciler.evaluate(record, now=resolved_now)
            reach = reach_by_id.get(
                record.record_id,
                MemoryReachability(record_id=record.record_id),
            )
            blockers: list[str] = []
            if reach.roots:
                blockers.append("reachable-from-root")
            if reach.legal_hold:
                blockers.append("legal-hold")
            if reach.audit_required:
                blockers.append("audit-required")
            if (
                reach.retention_until is not None
                and reach.retention_until > resolved_now
            ):
                blockers.append("retention-window-active")

            reasons = list(decision.reasons)
            if blockers:
                reasons.extend(blockers)
                if decision.action is MemoryAction.TOMBSTONE:
                    reasons.append("deletion-blocked")
                    disposition = MemoryGCDisposition.REVIEW
                elif decision.action is MemoryAction.REVIEW:
                    disposition = MemoryGCDisposition.REVIEW
                else:
                    disposition = MemoryGCDisposition.RETAIN
            elif decision.action is MemoryAction.TOMBSTONE:
                disposition = MemoryGCDisposition.TOMBSTONE
            elif decision.action is MemoryAction.REVIEW:
                disposition = MemoryGCDisposition.REVIEW
            else:
                disposition = MemoryGCDisposition.RETAIN

            entries.append(
                MemoryGCEntry(
                    record_id=record.record_id,
                    disposition=disposition,
                    quality_action=decision.action,
                    reasons=tuple(dict.fromkeys(reasons)),
                )
            )

        return MemoryGCPlan(
            generated_at=resolved_now,
            entries=tuple(entries),
        )


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
