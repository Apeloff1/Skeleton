"""Fail-closed required-gate authority for P1 promotion.

This contract evaluates workflow observations against a repository-owned
authority map. It does not query GitHub and it does not grant promotion
authority; callers must provide explicit observations for one exact commit.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from .canonical import EvidenceRef


_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/ -]*$")


class PromotionGateError(ValueError):
    """Required-gate authority input is malformed."""


def _text(value: object, field: str, *, max_length: int = 512) -> str:
    if not isinstance(value, str) or not value:
        raise PromotionGateError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise PromotionGateError(f"{field} must be normalized")
    if len(value) > max_length:
        raise PromotionGateError(f"{field} exceeds maximum length")
    return value


def _sha(value: object, field: str) -> str:
    text = _text(value, field, max_length=40)
    if not _SHA_RE.fullmatch(text):
        raise PromotionGateError(
            f"{field} must be a lowercase 40-character git SHA"
        )
    return text


def _utc(value: object, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise PromotionGateError(f"{field} must be timezone-aware")
    if value.utcoffset() is None:
        raise PromotionGateError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def canonical_digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


@dataclass(frozen=True, slots=True)
class GateObservation:
    workflow_name: str
    head_sha: str
    run_id: str
    run_attempt: int
    event: str
    status: str
    conclusion: str
    completed_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "workflow_name",
            _text(self.workflow_name, "workflow_name", max_length=256),
        )
        object.__setattr__(self, "head_sha", _sha(self.head_sha, "head_sha"))
        object.__setattr__(
            self,
            "run_id",
            _text(self.run_id, "run_id", max_length=128),
        )
        if (
            isinstance(self.run_attempt, bool)
            or not isinstance(self.run_attempt, int)
            or self.run_attempt < 1
        ):
            raise PromotionGateError(
                "run_attempt must be a positive integer"
            )
        object.__setattr__(
            self,
            "event",
            _text(self.event, "event", max_length=64),
        )
        object.__setattr__(
            self,
            "status",
            _text(self.status, "status", max_length=64),
        )
        object.__setattr__(
            self,
            "conclusion",
            _text(self.conclusion, "conclusion", max_length=64),
        )
        object.__setattr__(
            self,
            "completed_at",
            _utc(self.completed_at, "completed_at"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "workflow_name": self.workflow_name,
            "head_sha": self.head_sha,
            "run_id": self.run_id,
            "run_attempt": self.run_attempt,
            "event": self.event,
            "status": self.status,
            "conclusion": self.conclusion,
            "completed_at": self.completed_at.isoformat().replace(
                "+00:00", "Z"
            ),
        }


@dataclass(frozen=True, slots=True)
class GateAuthorityDecision:
    target_sha: str
    authority_digest: str
    observations_digest: str
    accepted: bool
    required_gate_count: int
    passing_gate_count: int
    missing: tuple[str, ...] = ()
    stale: tuple[str, ...] = ()
    duplicate: tuple[str, ...] = ()
    wrong_event: tuple[str, ...] = ()
    nonterminal: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()

    def _digest_payload(self) -> dict[str, Any]:
        return {
            "target_sha": self.target_sha,
            "authority_digest": self.authority_digest,
            "observations_digest": self.observations_digest,
            "accepted": self.accepted,
            "required_gate_count": self.required_gate_count,
            "passing_gate_count": self.passing_gate_count,
            "missing": list(self.missing),
            "stale": list(self.stale),
            "duplicate": list(self.duplicate),
            "wrong_event": list(self.wrong_event),
            "nonterminal": list(self.nonterminal),
            "rejected": list(self.rejected),
        }

    @property
    def decision_digest(self) -> str:
        return canonical_digest(self._digest_payload())

    def accepted_evidence_ref(
        self,
        *,
        source: str = "p1:required-gate-authority",
    ) -> EvidenceRef:
        if not self.accepted:
            raise PromotionGateError(
                "rejected gate authority decision cannot become promotion evidence"
            )
        return EvidenceRef(
            source=_text(source, "source", max_length=2048),
            digest=self.decision_digest,
            category="promotion_gate_authority",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **self._digest_payload(),
            "decision_digest": self.decision_digest,
        }


def _required_gates(authority: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    gates = authority.get("gates")
    if not isinstance(gates, list) or not gates:
        raise PromotionGateError("authority gates must be a non-empty list")
    required = [
        gate
        for gate in gates
        if isinstance(gate, Mapping)
        and gate.get("required_for_terminal_p1_promotion") is True
    ]
    if not required:
        raise PromotionGateError("authority defines no required gates")
    names = [gate.get("workflow_name") for gate in required]
    if any(not isinstance(name, str) or not name for name in names):
        raise PromotionGateError("required gates need workflow_name")
    if len(names) != len(set(names)):
        raise PromotionGateError("required workflow names must be unique")
    return required


def evaluate_required_gates(
    authority: Mapping[str, Any],
    observations: Iterable[GateObservation],
    *,
    target_sha: str,
) -> GateAuthorityDecision:
    """Evaluate one exact-head required-gate observation set."""

    target = _sha(target_sha, "target_sha")
    required = _required_gates(authority)
    expected_event = _text(
        authority.get("target_event"),
        "authority.target_event",
        max_length=64,
    )

    raw_observations = tuple(observations)
    if not all(
        isinstance(item, GateObservation)
        for item in raw_observations
    ):
        raise PromotionGateError(
            "observations must contain GateObservation values"
        )

    normalized = sorted(
        (item.as_dict() for item in raw_observations),
        key=lambda row: (
            row["workflow_name"],
            row["head_sha"],
            row["run_id"],
            row["run_attempt"],
        ),
    )
    authority_digest = canonical_digest(dict(authority))
    observations_digest = canonical_digest(normalized)

    by_name: dict[str, list[GateObservation]] = {}
    for item in raw_observations:
        by_name.setdefault(item.workflow_name, []).append(item)

    missing: list[str] = []
    stale: list[str] = []
    duplicate: list[str] = []
    wrong_event: list[str] = []
    nonterminal: list[str] = []
    rejected: list[str] = []
    passing = 0

    for gate in required:
        name = str(gate["workflow_name"])
        observations_for_gate = by_name.get(name, [])
        exact = [
            item
            for item in observations_for_gate
            if item.head_sha == target
        ]

        if not observations_for_gate:
            missing.append(name)
            continue
        if not exact:
            stale.append(name)
            continue
        if len(exact) != 1:
            duplicate.append(name)
            continue

        item = exact[0]
        if item.event != expected_event:
            wrong_event.append(name)
            continue

        accepted_statuses = gate.get("accepted_statuses")
        accepted_conclusions = gate.get("accepted_conclusions")
        if not isinstance(accepted_statuses, list) or not accepted_statuses:
            raise PromotionGateError(
                f"{name}: accepted_statuses must be non-empty"
            )
        if (
            not isinstance(accepted_conclusions, list)
            or not accepted_conclusions
        ):
            raise PromotionGateError(
                f"{name}: accepted_conclusions must be non-empty"
            )
        if item.status not in accepted_statuses:
            nonterminal.append(name)
            continue
        if item.conclusion not in accepted_conclusions:
            rejected.append(name)
            continue
        passing += 1

    accepted = not any(
        (missing, stale, duplicate, wrong_event, nonterminal, rejected)
    ) and passing == len(required)

    return GateAuthorityDecision(
        target_sha=target,
        authority_digest=authority_digest,
        observations_digest=observations_digest,
        accepted=accepted,
        required_gate_count=len(required),
        passing_gate_count=passing,
        missing=tuple(sorted(missing)),
        stale=tuple(sorted(stale)),
        duplicate=tuple(sorted(duplicate)),
        wrong_event=tuple(sorted(wrong_event)),
        nonterminal=tuple(sorted(nonterminal)),
        rejected=tuple(sorted(rejected)),
    )
