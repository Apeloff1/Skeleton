"""P3 multi-agent coordination, delegation economics and disagreement control."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Iterable, Mapping, Sequence


class CoordinationError(RuntimeError):
    pass


def _id(value: object, field: str, *, maximum: int = 192) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text")
    text = value.strip()
    if not text or len(text) > maximum:
        raise ValueError(f"{field} must be non-empty bounded text")
    return text


def _refs(values: Iterable[str], field: str, *, required: bool = False) -> tuple[str, ...]:
    normalized = tuple(sorted({_id(item, field) for item in values}))
    if required and not normalized:
        raise ValueError(f"{field} requires at least one value")
    if len(normalized) > 128:
        raise ValueError(f"{field} exceeds maximum cardinality")
    return normalized


def _decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool):
        raise TypeError(f"{field} must be numeric")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be finite decimal") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError(f"{field} must be finite non-negative decimal")
    return amount.quantize(Decimal("0.000001"))


def _ratio(value: object, field: str) -> Decimal:
    amount = _decimal(value, field)
    if amount > Decimal("1"):
        raise ValueError(f"{field} must be in [0,1]")
    return amount


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


def _scope_overlap(left: str, right: str) -> bool:
    a = left.rstrip("/")
    b = right.rstrip("/")
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


@dataclass(frozen=True, slots=True)
class AgentSeat:
    agent_id: str
    role: str
    capabilities: tuple[str, ...]
    authority_scopes: tuple[str, ...]
    mutation_scopes: tuple[str, ...] = ()
    max_cost: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _id(self.agent_id, "agent_id"))
        object.__setattr__(self, "role", _id(self.role, "role"))
        object.__setattr__(
            self,
            "capabilities",
            _refs(self.capabilities, "capability", required=True),
        )
        object.__setattr__(
            self,
            "authority_scopes",
            _refs(self.authority_scopes, "authority_scope", required=True),
        )
        object.__setattr__(
            self,
            "mutation_scopes",
            _refs(self.mutation_scopes, "mutation_scope"),
        )
        object.__setattr__(self, "max_cost", _decimal(self.max_cost, "max_cost"))


@dataclass(frozen=True, slots=True)
class HandoffPacket:
    handoff_id: str
    task_id: str
    sender_id: str
    receiver_id: str
    delegated_capabilities: tuple[str, ...]
    delegated_authority_scopes: tuple[str, ...]
    conflict_domains: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    max_cost: Decimal

    def __post_init__(self) -> None:
        for field in ("handoff_id", "task_id", "sender_id", "receiver_id"):
            object.__setattr__(self, field, _id(getattr(self, field), field))
        if self.sender_id == self.receiver_id:
            raise ValueError("handoff sender and receiver must differ")
        object.__setattr__(
            self,
            "delegated_capabilities",
            _refs(self.delegated_capabilities, "delegated_capability", required=True),
        )
        object.__setattr__(
            self,
            "delegated_authority_scopes",
            _refs(
                self.delegated_authority_scopes,
                "delegated_authority_scope",
                required=True,
            ),
        )
        object.__setattr__(
            self,
            "conflict_domains",
            _refs(self.conflict_domains, "conflict_domain"),
        )
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "handoff_evidence_ref", required=True),
        )
        object.__setattr__(self, "max_cost", _decimal(self.max_cost, "max_cost"))


@dataclass(frozen=True, slots=True)
class DelegationReceipt:
    handoff_id: str
    permitted: bool
    reason_code: str
    sender_id: str
    receiver_id: str
    delegated_capabilities: tuple[str, ...]
    delegated_authority_scopes: tuple[str, ...]
    max_cost: Decimal
    receipt_digest: str


def delegate(
    packet: HandoffPacket,
    *,
    sender: AgentSeat,
    receiver: AgentSeat,
) -> DelegationReceipt:
    if packet.sender_id != sender.agent_id or packet.receiver_id != receiver.agent_id:
        raise CoordinationError("handoff identity does not match agent seats")

    permitted = True
    reason = "permitted"
    if not set(packet.delegated_capabilities) <= set(sender.capabilities):
        permitted, reason = False, "sender_capability_amplification"
    elif not set(packet.delegated_capabilities) <= set(receiver.capabilities):
        permitted, reason = False, "receiver_capability_missing"
    elif not set(packet.delegated_authority_scopes) <= set(sender.authority_scopes):
        permitted, reason = False, "sender_authority_amplification"
    elif not set(packet.delegated_authority_scopes) <= set(receiver.authority_scopes):
        permitted, reason = False, "receiver_authority_missing"
    elif packet.max_cost > sender.max_cost or packet.max_cost > receiver.max_cost:
        permitted, reason = False, "delegation_cost_budget_exceeded"

    material = {
        "handoff_id": packet.handoff_id,
        "permitted": permitted,
        "reason_code": reason,
        "sender_id": sender.agent_id,
        "receiver_id": receiver.agent_id,
        "delegated_capabilities": list(packet.delegated_capabilities),
        "delegated_authority_scopes": list(packet.delegated_authority_scopes),
        "max_cost": str(packet.max_cost),
        "evidence_refs": list(packet.evidence_refs),
    }
    return DelegationReceipt(
        handoff_id=packet.handoff_id,
        permitted=permitted,
        reason_code=reason,
        sender_id=sender.agent_id,
        receiver_id=receiver.agent_id,
        delegated_capabilities=packet.delegated_capabilities,
        delegated_authority_scopes=packet.delegated_authority_scopes,
        max_cost=packet.max_cost,
        receipt_digest=_digest(material),
    )


@dataclass(frozen=True, slots=True)
class CoordinationPlan:
    seats: tuple[AgentSeat, ...]
    handoffs: tuple[HandoffPacket, ...]
    delegation_receipts: tuple[DelegationReceipt, ...]
    conflict_pairs: tuple[tuple[str, str, str], ...]
    plan_digest: str

    @property
    def executable(self) -> bool:
        return (
            all(receipt.permitted for receipt in self.delegation_receipts)
            and not self.conflict_pairs
        )


def build_coordination_plan(
    seats: Sequence[AgentSeat],
    handoffs: Sequence[HandoffPacket],
) -> CoordinationPlan:
    if not seats:
        raise CoordinationError("coordination plan requires agent seats")
    by_id = {seat.agent_id: seat for seat in seats}
    if len(by_id) != len(seats):
        raise CoordinationError("agent seat identities must be unique")
    handoff_ids = [item.handoff_id for item in handoffs]
    if len(handoff_ids) != len(set(handoff_ids)):
        raise CoordinationError("handoff identities must be unique")

    receipts: list[DelegationReceipt] = []
    for packet in handoffs:
        sender = by_id.get(packet.sender_id)
        receiver = by_id.get(packet.receiver_id)
        if sender is None or receiver is None:
            raise CoordinationError("handoff references unknown agent")
        receipts.append(delegate(packet, sender=sender, receiver=receiver))

    conflicts: set[tuple[str, str, str]] = set()
    ordered = sorted(seats, key=lambda item: item.agent_id)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            for lscope in left.mutation_scopes:
                for rscope in right.mutation_scopes:
                    if _scope_overlap(lscope, rscope):
                        conflicts.add(
                            (
                                left.agent_id,
                                right.agent_id,
                                min(lscope, rscope),
                            )
                        )
    normalized_seats = tuple(ordered)
    normalized_handoffs = tuple(sorted(handoffs, key=lambda item: item.handoff_id))
    normalized_receipts = tuple(sorted(receipts, key=lambda item: item.handoff_id))
    normalized_conflicts = tuple(sorted(conflicts))
    material = {
        "seats": [
            {
                "agent_id": item.agent_id,
                "role": item.role,
                "capabilities": list(item.capabilities),
                "authority_scopes": list(item.authority_scopes),
                "mutation_scopes": list(item.mutation_scopes),
                "max_cost": str(item.max_cost),
            }
            for item in normalized_seats
        ],
        "handoffs": [
            {
                "handoff_id": item.handoff_id,
                "task_id": item.task_id,
                "sender_id": item.sender_id,
                "receiver_id": item.receiver_id,
                "delegated_capabilities": list(item.delegated_capabilities),
                "delegated_authority_scopes": list(item.delegated_authority_scopes),
                "conflict_domains": list(item.conflict_domains),
                "max_cost": str(item.max_cost),
                "evidence_refs": list(item.evidence_refs),
            }
            for item in normalized_handoffs
        ],
        "receipts": [
            {
                "handoff_id": item.handoff_id,
                "permitted": item.permitted,
                "reason_code": item.reason_code,
                "receipt_digest": item.receipt_digest,
            }
            for item in normalized_receipts
        ],
        "conflicts": [list(item) for item in normalized_conflicts],
    }
    return CoordinationPlan(
        seats=normalized_seats,
        handoffs=normalized_handoffs,
        delegation_receipts=normalized_receipts,
        conflict_pairs=normalized_conflicts,
        plan_digest=_digest(material),
    )


@dataclass(frozen=True, slots=True)
class PerformanceRecord:
    agent_id: str
    task_id: str
    config_digest: str
    model_digest: str
    completion: Decimal
    correctness: Decimal
    recovery: Decimal
    cost: Decimal
    human_interventions: int
    delegation_cost: Decimal
    evidence_refs: tuple[str, ...]
    record_digest: str


def record_performance(
    *,
    agent_id: str,
    task_id: str,
    config_digest: str,
    model_digest: str,
    completion: object,
    correctness: object,
    recovery: object,
    cost: object,
    human_interventions: int,
    delegation_cost: object,
    evidence_refs: Iterable[str],
) -> PerformanceRecord:
    aid = _id(agent_id, "agent_id")
    tid = _id(task_id, "task_id")
    cd = _id(config_digest, "config_digest", maximum=64)
    md = _id(model_digest, "model_digest", maximum=64)
    for name, value in (("config_digest", cd), ("model_digest", md)):
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError(f"{name} must be lowercase sha256")
    c1 = _ratio(completion, "completion")
    c2 = _ratio(correctness, "correctness")
    c3 = _ratio(recovery, "recovery")
    money = _decimal(cost, "cost")
    delegated = _decimal(delegation_cost, "delegation_cost")
    if (
        isinstance(human_interventions, bool)
        or not isinstance(human_interventions, int)
        or human_interventions < 0
    ):
        raise ValueError("human_interventions must be non-negative integer")
    refs = _refs(evidence_refs, "performance_evidence_ref", required=True)
    material = {
        "agent_id": aid,
        "task_id": tid,
        "config_digest": cd,
        "model_digest": md,
        "completion": str(c1),
        "correctness": str(c2),
        "recovery": str(c3),
        "cost": str(money),
        "human_interventions": human_interventions,
        "delegation_cost": str(delegated),
        "evidence_refs": list(refs),
    }
    return PerformanceRecord(
        agent_id=aid,
        task_id=tid,
        config_digest=cd,
        model_digest=md,
        completion=c1,
        correctness=c2,
        recovery=c3,
        cost=money,
        human_interventions=human_interventions,
        delegation_cost=delegated,
        evidence_refs=refs,
        record_digest=_digest(material),
    )


@dataclass(frozen=True, slots=True)
class EvidencePosition:
    agent_id: str
    position: str
    evidence_refs: tuple[str, ...]
    confidence: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "agent_id", _id(self.agent_id, "agent_id"))
        object.__setattr__(self, "position", _id(self.position, "position"))
        object.__setattr__(
            self,
            "evidence_refs",
            _refs(self.evidence_refs, "position_evidence_ref", required=True),
        )
        object.__setattr__(self, "confidence", _ratio(self.confidence, "confidence"))


@dataclass(frozen=True, slots=True)
class DisagreementDecision:
    status: str
    selected_position: str | None
    preserved_positions: tuple[EvidencePosition, ...]
    escalation_required: bool
    reason_code: str
    decision_digest: str


def decide_disagreement(
    positions: Sequence[EvidencePosition],
    *,
    impact: str,
    consensus_threshold: Decimal = Decimal("0.80"),
) -> DisagreementDecision:
    if impact not in {"low", "medium", "high", "critical"}:
        raise ValueError("impact must be low/medium/high/critical")
    if len(positions) < 2:
        raise CoordinationError("disagreement decision requires at least two positions")
    agents = [item.agent_id for item in positions]
    if len(agents) != len(set(agents)):
        raise CoordinationError("positions must come from independent agent identities")
    threshold = _ratio(consensus_threshold, "consensus_threshold")
    groups: dict[str, list[EvidencePosition]] = {}
    for item in positions:
        groups.setdefault(item.position, []).append(item)
    ranked = sorted(
        groups.items(),
        key=lambda item: (-len(item[1]), -sum(x.confidence for x in item[1]), item[0]),
    )
    winner, members = ranked[0]
    share = Decimal(len(members)) / Decimal(len(positions))
    unresolved = len(groups) > 1 and share < threshold
    high_impact = impact in {"high", "critical"}
    escalate_flag = unresolved and high_impact
    selected = None if escalate_flag else winner
    status = "escalated" if escalate_flag else "resolved"
    reason = (
        "high_impact_disagreement_requires_independent_escalation"
        if escalate_flag
        else "evidence_preserved_consensus_selected"
    )
    preserved = tuple(sorted(positions, key=lambda item: (item.position, item.agent_id)))
    material = {
        "status": status,
        "selected_position": selected,
        "impact": impact,
        "threshold": str(threshold),
        "positions": [
            {
                "agent_id": item.agent_id,
                "position": item.position,
                "evidence_refs": list(item.evidence_refs),
                "confidence": str(item.confidence),
            }
            for item in preserved
        ],
        "reason_code": reason,
    }
    return DisagreementDecision(
        status=status,
        selected_position=selected,
        preserved_positions=preserved,
        escalation_required=escalate_flag,
        reason_code=reason,
        decision_digest=_digest(material),
    )


__all__ = [
    "AgentSeat",
    "CoordinationError",
    "CoordinationPlan",
    "DelegationReceipt",
    "DisagreementDecision",
    "EvidencePosition",
    "HandoffPacket",
    "PerformanceRecord",
    "build_coordination_plan",
    "decide_disagreement",
    "delegate",
    "record_performance",
]
