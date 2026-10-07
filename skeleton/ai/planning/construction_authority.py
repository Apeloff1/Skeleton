"""Deterministic construction-packet and technology-radar authority for P3.

This module produces derived planning artifacts only.  It intentionally has no
completion, maturity, signing, or runtime-promotion authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import hashlib
import json
from typing import Mapping, Sequence


class ConstructionAuthorityError(RuntimeError):
    pass


def _text(name: str, value: object, limit: int = 1024) -> str:
    text = str(value).strip()
    if not text:
        raise ConstructionAuthorityError(f"{name} must be non-empty")
    if len(text) > limit:
        raise ConstructionAuthorityError(f"{name} exceeds size limit")
    return text


def _refs(name: str, values: Sequence[str], *, minimum: int = 1) -> tuple[str, ...]:
    refs = tuple(dict.fromkeys(_text(name, value, 512) for value in values))
    if len(refs) < minimum:
        raise ConstructionAuthorityError(f"{name} requires at least {minimum} refs")
    return refs


def _stable_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PacketSection:
    section_id: str
    title: str
    references: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "section_id", _text("section_id", self.section_id, 128))
        object.__setattr__(self, "title", _text("title", self.title, 256))
        object.__setattr__(
            self,
            "references",
            _refs("packet_reference", self.references),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "references": list(self.references),
        }


@dataclass(frozen=True, slots=True)
class ConstructionPacket:
    packet_id: str
    source_digest: str
    generated_from: tuple[str, ...]
    sections: tuple[PacketSection, ...]
    packet_digest: str
    completion_authority: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "packet_id", _text("packet_id", self.packet_id, 256))
        if len(self.source_digest) != 64:
            raise ConstructionAuthorityError("source_digest must be sha256")
        object.__setattr__(
            self,
            "generated_from",
            _refs("generated_from", self.generated_from, minimum=2),
        )
        if not self.sections:
            raise ConstructionAuthorityError("construction packet requires sections")
        ids = [section.section_id for section in self.sections]
        if len(ids) != len(set(ids)):
            raise ConstructionAuthorityError("construction packet section ids must be unique")
        if len(self.packet_digest) != 64:
            raise ConstructionAuthorityError("packet_digest must be sha256")
        if self.completion_authority is not False:
            raise ConstructionAuthorityError("construction packets never own completion authority")


class ConstructionPacketBuilder:
    REQUIRED_SECTION_IDS = (
        "authority",
        "scope",
        "work",
        "evidence",
        "unresolved",
        "handoff",
    )

    def build(
        self,
        *,
        packet_id: str,
        sources: Mapping[str, object],
        authority_refs: Sequence[str],
        scope_refs: Sequence[str],
        task_refs: Sequence[str],
        evidence_refs: Sequence[str],
        unresolved_refs: Sequence[str],
        handoff_refs: Sequence[str],
    ) -> ConstructionPacket:
        if not isinstance(sources, Mapping) or not sources:
            raise ConstructionAuthorityError("construction packet requires source snapshot")
        normalized_sources = {str(k): sources[k] for k in sorted(sources)}
        source_digest = _digest(normalized_sources)
        generated_from = tuple(sorted(normalized_sources))
        sections = (
            PacketSection("authority", "Authority", tuple(authority_refs)),
            PacketSection("scope", "Scope", tuple(scope_refs)),
            PacketSection("work", "Work", tuple(task_refs)),
            PacketSection("evidence", "Evidence", tuple(evidence_refs)),
            PacketSection("unresolved", "Unresolved", tuple(unresolved_refs)),
            PacketSection("handoff", "Handoff", tuple(handoff_refs)),
        )
        payload = {
            "packet_id": _text("packet_id", packet_id, 256),
            "source_digest": source_digest,
            "generated_from": generated_from,
            "sections": [section.as_dict() for section in sections],
            "completion_authority": False,
        }
        return ConstructionPacket(
            packet_id=payload["packet_id"],
            source_digest=source_digest,
            generated_from=generated_from,
            sections=sections,
            packet_digest=_digest(payload),
            completion_authority=False,
        )


class RadarState(str, Enum):
    WATCH = "watch"
    TRIAL = "trial"
    ADOPT = "adopt"
    HOLD = "hold"
    EXIT = "exit"


_ALLOWED_TRANSITIONS = {
    RadarState.WATCH: {RadarState.TRIAL, RadarState.HOLD, RadarState.EXIT},
    RadarState.TRIAL: {RadarState.ADOPT, RadarState.HOLD, RadarState.EXIT},
    RadarState.ADOPT: {RadarState.HOLD, RadarState.EXIT},
    RadarState.HOLD: {RadarState.WATCH, RadarState.TRIAL, RadarState.EXIT},
    RadarState.EXIT: set(),
}


@dataclass(frozen=True, slots=True)
class TechnologyCandidate:
    candidate_id: str
    state: RadarState
    evidence_refs: tuple[str, ...]
    exit_criteria: tuple[str, ...]
    review_after_cycles: int
    architecture_decision_ref: str | None = None
    vendor_dependency: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _text("candidate_id", self.candidate_id, 256))
        if not isinstance(self.state, RadarState):
            object.__setattr__(self, "state", RadarState(str(self.state)))
        object.__setattr__(
            self,
            "evidence_refs",
            _refs("technology_evidence_ref", self.evidence_refs),
        )
        object.__setattr__(
            self,
            "exit_criteria",
            _refs("technology_exit_criterion", self.exit_criteria),
        )
        if (
            isinstance(self.review_after_cycles, bool)
            or not isinstance(self.review_after_cycles, int)
            or not 1 <= self.review_after_cycles <= 64
        ):
            raise ConstructionAuthorityError("review_after_cycles must be in [1, 64]")
        if self.architecture_decision_ref is not None:
            object.__setattr__(
                self,
                "architecture_decision_ref",
                _text("architecture_decision_ref", self.architecture_decision_ref, 512),
            )
        if self.vendor_dependency is not None:
            object.__setattr__(
                self,
                "vendor_dependency",
                _text("vendor_dependency", self.vendor_dependency, 256),
            )


@dataclass(frozen=True, slots=True)
class RadarDecision:
    candidate_id: str
    from_state: RadarState
    to_state: RadarState
    evidence_refs: tuple[str, ...]
    architecture_decision_ref: str | None
    decision_digest: str


class TechnologyRadar:
    def transition(
        self,
        candidate: TechnologyCandidate,
        target: RadarState,
        *,
        evidence_refs: Sequence[str],
        architecture_decision_ref: str | None = None,
    ) -> tuple[TechnologyCandidate, RadarDecision]:
        if not isinstance(target, RadarState):
            target = RadarState(str(target))
        if target not in _ALLOWED_TRANSITIONS[candidate.state]:
            raise ConstructionAuthorityError(
                f"technology transition not allowed: {candidate.state.value}->{target.value}"
            )
        refs = _refs("radar_decision_evidence", evidence_refs, minimum=2)
        adr = architecture_decision_ref or candidate.architecture_decision_ref
        if target is RadarState.ADOPT:
            if adr is None or not str(adr).startswith("adr:"):
                raise ConstructionAuthorityError("technology adoption requires architecture decision")
            if candidate.vendor_dependency and not any(
                "exit" in criterion.lower() or "migration" in criterion.lower()
                for criterion in candidate.exit_criteria
            ):
                raise ConstructionAuthorityError(
                    "vendor-backed adoption requires explicit exit/migration criterion"
                )
        payload = {
            "candidate_id": candidate.candidate_id,
            "from_state": candidate.state.value,
            "to_state": target.value,
            "evidence_refs": refs,
            "architecture_decision_ref": adr,
            "review_after_cycles": candidate.review_after_cycles,
            "exit_criteria": candidate.exit_criteria,
        }
        decision = RadarDecision(
            candidate_id=candidate.candidate_id,
            from_state=candidate.state,
            to_state=target,
            evidence_refs=refs,
            architecture_decision_ref=adr,
            decision_digest=_digest(payload),
        )
        return (
            replace(
                candidate,
                state=target,
                evidence_refs=tuple(dict.fromkeys(candidate.evidence_refs + refs)),
                architecture_decision_ref=adr,
            ),
            decision,
        )


__all__ = [
    "ConstructionAuthorityError",
    "ConstructionPacket",
    "ConstructionPacketBuilder",
    "PacketSection",
    "RadarDecision",
    "RadarState",
    "TechnologyCandidate",
    "TechnologyRadar",
]
