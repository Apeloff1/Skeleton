"""Fail-closed capability catalog. Intent and live evidence are separate authorities."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Mapping


class Availability(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class Maturity(str, Enum):
    PLANNED = "planned"
    EXPERIMENTAL = "experimental"
    PRODUCTION = "production"


class CapabilityError(RuntimeError):
    pass


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    owner: str
    contract: str
    failure_modes: tuple[str, ...]
    obs: str
    security: str
    maturity: Maturity
    dependencies: tuple[str, ...] = ()
    guarantees: tuple[str, ...] = ()
    volume: str = "VOL-FILL"


@dataclass(frozen=True)
class CapabilityEvidence:
    capability_id: str
    revision: str
    availability: Availability
    guarantees: tuple[str, ...]
    digest: str
    reason: str


@dataclass
class CapabilityAvailability:
    capability_id: str
    availability: Availability
    reason: str
    descriptor: CapabilityDescriptor
    evidence: CapabilityEvidence | None = None


def _d(
    cid: str,
    owner: str,
    contract: str,
    modes: tuple[str, ...],
    deps: tuple[str, ...] = (),
    maturity: Maturity = Maturity.PRODUCTION,
    volume: str = "VOL-FILL",
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=cid,
        owner=owner,
        contract=contract,
        failure_modes=modes,
        obs=f"card.law={cid}",
        security="fail-closed; no secret; no coin; no stored prose",
        maturity=maturity,
        dependencies=deps,
        guarantees=("deterministic", "cpu", "no-torch"),
        volume=volume,
    )


DESCRIPTORS: tuple[CapabilityDescriptor, ...] = (
    _d("AIFT-NUMERICS", "ai.numerics", "rmsnorm+silu+softmax finite", ("non-finite", "empty")),
    _d("AIFT-LINALG", "ai.numerics", "householder QR reconstructs", ("rank-drop",), ("AIFT-NUMERICS",)),
    _d("AIFT-OPTIMIZE", "ai.numerics", "clipped CG on SPD", ("stall",), ("AIFT-LINALG",)),
    _d("AIFT-POINTER-PARSE", "ai.laws", "pointer clauses, N-cap 8", ("stored-prose",)),
    _d("AIFT-CLIPPED-G", "ai.laws", "G via MHC*S with trajectory", ("gb-16",), ("AIFT-POINTER-PARSE",)),
    _d("AIFT-MEMORY", "ai.planes", "pointer merkle memory", ("stored-prose",), ("AIFT-POINTER-PARSE",), volume="VOL-MEMORY"),
    _d("AIFT-RETRIEVAL", "ai.planes", "pointer overlap retrieval", ("empty-index",), ("AIFT-MEMORY",)),
    _d("AIFT-SKILLS", "ai.planes", "named skill contract bind", ("unnamed",)),
    _d("AIFT-OUTBOX", "ai.planes", "idempotent durable outbox", ("coin",), ("AIFT-POINTER-PARSE",)),
    _d("AIFT-CONSENSUS", "ai.planes", "local root quorum, no chain", ("quorum",), ("AIFT-MEMORY",)),
    _d("AIFT-ADMISSION", "ai.planes", "unowned tracked file fails", ("unowned",)),
    _d("AIFT-COMPENSATION", "ai.planes", "effect has distinct undo", ("alias-undo",)),
    _d("AIFT-RECOVERY", "ai.planes", "resume from checkpoint", ("missing-checkpoint",)),
    _d("AIFT-PROVIDERS", "ai.planes", "cpu provider, no torch authority", ("live-secret",)),
    _d("AIFT-ERA-BIND", "ai.organs", "title maps to HOUSE_ERA", ("unbound-title",)),
    _d("AIFT-ORGAN-SPEAK", "ai.organs", "speak returns pointer voice", ("unknown-organ",), ("AIFT-POINTER-PARSE",)),
    _d("AIFT-ORGAN-REFER", "ai.organs", "refer cites era", ("unbound-title",), ("AIFT-ERA-BIND",)),
    _d("AIFT-ORGAN-IMPROVE", "ai.organs", "four-axis critique", ("missing-axis",)),
    _d("AIFT-ORGAN-ASCEND", "ai.organs", "rung increments", ()),
    _d("AIFT-ORGAN-PLAN", "ai.organs", "7-step forge plan", ("unbound-title",), ("AIFT-ERA-BIND",)),
    _d("AIFT-ORGAN-WALK", "ai.organs", "fieldwalk stores no prose", ("stored-prose",)),
    _d("AIFT-ORGAN-PICK", "ai.organs", "softmax pick", ("empty",), ("AIFT-NUMERICS",)),
    _d("AIFT-ORGAN-GENOS", "ai.organs", "helix pair emitted", ()),
    _d("AIFT-ORGAN-CUT", "ai.organs", "cut sets era", ("unbound-title",), ("AIFT-ERA-BIND",)),
    _d("AIFT-ORGAN-CONTACT", "ai.organs", "house-copy LoRA contact", ()),
    _d("AIFT-ORGAN-GOSSIP", "ai.organs", "merkle root, no chain", ("coin",), ("AIFT-MEMORY",)),
    _d("AIFT-ORGAN-OBSERVE", "ai.organs", "observe card carries G trajectory", ("gb-16",), ("AIFT-CLIPPED-G",)),
    _d("AIFT-ORGAN-FORGE", "ai.organs", "mass at most prior*1.1", ("mass-snowball",), ("AIFT-CLIPPED-G",)),
    _d("AIFT-ORGAN-LORA", "ai.organs", "attach rank-2 bank", ()),
    _d("AIFT-ORGAN-BEAM", "ai.organs", "beam width paths", ()),
    _d("AIFT-ORGAN-ACCUM", "ai.organs", "rmsnorm residual", ("empty",), ("AIFT-NUMERICS",)),
    _d("AIFT-HIVE-MERKLE", "ai.planes", "root history local", ("chain",), ("AIFT-CONSENSUS",)),
    _d("AIFT-CAPABILITY-INDEX", "ai.catalog", "owner contract failure_modes obs security", ("unowned",), ("AIFT-ADMISSION",)),
    _d("AIFT-ROUTER", "ai.catalog", "one router contract", ("third-router",), ("AIFT-ORGAN-PICK",)),
    _d("AIFT-SPECDEC", "ai.numerics", "accept-until-mismatch", ("mismatch-past-cap",), ("AIFT-NUMERICS",)),
    _d("AIFT-ECONOMY-HARBOR", "ai.planes", "lineage weights sum 1, no coin", ("coin", "weight-sum")),
    _d("AIFT-MOBILE-BANK", "ai.catalog", "heavy planes default off", ("gpu-on-mobile",)),
    _d("AIFT-SECURITY-ACE", "ai.laws", "ACE fail-close, no live secret", ("secret",)),
    _d("AIFT-QUEUE12", "ai.numerics", "RMSNorm+SiLU on QK", ("missing-kernel",), ("AIFT-NUMERICS",)),
    _d("AIFT-COGNITION", "ai.organs", "plan then cut then speak", ("era-miss",), ("AIFT-ORGAN-PLAN", "AIFT-ORGAN-CUT", "AIFT-ORGAN-SPEAK")),
    _d("AIFT-LEARNING", "ai.laws", "clipped-G step recorded", ("gb-16",), ("AIFT-CLIPPED-G",)),
    _d("AIFT-MODELING", "ai.numerics", "2-layer stand-in residual", ("empty",), ("AIFT-QUEUE12",)),
    _d("AIFT-TRAINING", "ai.laws", "absorb_steps default 4", ("over-absorb",), ("AIFT-LEARNING",)),
    _d("AIFT-MULTIMODAL", "ai.organs", "viseme binder data-only", ("executable-frame",)),
    _d("AIFT-RUNTIME-CONTRACTS", "ai.catalog", "unknown organ hit=0", ("silent-fallback",), ("AIFT-CAPABILITY-INDEX",)),
    _d("AIFT-DECISION", "ai.organs", "veto beats pick", ("veto-ignored",), ("AIFT-ORGAN-PICK",)),
    _d("AIFT-EVIDENCE", "ai.catalog", "missing evidence stays unavailable", ("silent-available",), ("AIFT-CAPABILITY-INDEX",)),
    _d("AIFT-COORDINATION", "ai.planes", "peer roots tournament N-cap 8", ("over-cap",), ("AIFT-CONSENSUS",)),
)


class CapabilityMap:
    def __init__(self, descriptors: tuple[CapabilityDescriptor, ...] = DESCRIPTORS) -> None:
        ids = [d.capability_id for d in descriptors]
        if len(ids) != len(set(ids)):
            raise CapabilityError("duplicate capability id")
        self.descriptors = {d.capability_id: d for d in descriptors}
        self.evidence: dict[str, CapabilityEvidence] = {}

    def stamp(self, evidence: CapabilityEvidence) -> None:
        if evidence.capability_id not in self.descriptors:
            raise CapabilityError(f"unknown {evidence.capability_id}")
        desc = self.descriptors[evidence.capability_id]
        if evidence.revision != desc.contract:
            raise CapabilityError("revision mismatch")
        self.evidence[evidence.capability_id] = evidence

    def resolve(self, capability_id: str, seen: set[str] | None = None) -> CapabilityAvailability:
        if capability_id not in self.descriptors:
            raise CapabilityError(f"unknown {capability_id}")
        seen = set() if seen is None else set(seen)
        if capability_id in seen:
            return CapabilityAvailability(capability_id, Availability.UNAVAILABLE, "cycle", self.descriptors[capability_id])
        seen.add(capability_id)
        desc = self.descriptors[capability_id]
        for dep in desc.dependencies:
            parent = self.resolve(dep, seen)
            if parent.availability != Availability.AVAILABLE:
                return CapabilityAvailability(capability_id, Availability.UNAVAILABLE, f"dep {dep}", desc)
        ev = self.evidence.get(capability_id)
        if ev is None:
            return CapabilityAvailability(capability_id, Availability.UNAVAILABLE, "no evidence", desc)
        if ev.availability != Availability.AVAILABLE:
            return CapabilityAvailability(capability_id, ev.availability, ev.reason, desc, ev)
        missing = [g for g in desc.guarantees if g not in ev.guarantees]
        if missing:
            return CapabilityAvailability(capability_id, Availability.DEGRADED, "guarantee gap", desc, ev)
        return CapabilityAvailability(capability_id, Availability.AVAILABLE, ev.reason, desc, ev)

    def snapshot(self) -> list[dict]:
        rows = []
        for cid in self.descriptors:
            row = self.resolve(cid)
            rows.append(
                {
                    "id": cid,
                    "availability": row.availability.value,
                    "reason": row.reason,
                    "owner": row.descriptor.owner,
                    "maturity": row.descriptor.maturity.value,
                    "volume": row.descriptor.volume,
                }
            )
        return rows


Probe = Callable[[], CapabilityEvidence]
PROBES: dict[str, Probe] = {}


def register_probe(capability_id: str, fn: Probe) -> None:
    PROBES[capability_id] = fn
