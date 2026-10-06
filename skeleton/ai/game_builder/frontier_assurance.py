"""Third-generation assurance primitives for the AI Game Builder.

These controls sit above the core duel loop.  They are deterministic, bounded,
and intentionally do not make creative decisions themselves.  They preserve
causal obligations, independent evaluation, alternative hypotheses, evidence
freshness, and long-horizon convergence signals used by the promotion plane.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable, Mapping, Sequence

from .contracts import EvaluatorProvenance, EffortMode, canonical_digest


class FrontierAssuranceError(ValueError):
    """Raised when frontier-assurance invariants fail closed."""


def _stable(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value.strip()) < 8:
        raise FrontierAssuranceError(f"{label} must be stable non-empty text")
    return value.strip()


def _unit(value: float, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FrontierAssuranceError(f"{label} must be numeric")
    out = float(value)
    if not 0.0 <= out <= 1.0:
        raise FrontierAssuranceError(f"{label} must be within [0,1]")
    return out


class ObligationSeverity(IntEnum):
    NOTE = 1
    MATERIAL = 5
    CRITICAL = 10


@dataclass(frozen=True, slots=True)
class CausalObligation:
    obligation_id: str
    premise_ids: tuple[str, ...]
    consequence_ids: tuple[str, ...]
    evidence_digest: str
    authority_provenance: EvaluatorProvenance
    severity: ObligationSeverity = ObligationSeverity.MATERIAL
    resolved: bool = False
    resolution_digest: str | None = None
    resolution_authority: EvaluatorProvenance | None = None

    def __post_init__(self) -> None:
        _stable(self.obligation_id, "obligation_id")
        _stable(self.evidence_digest, "evidence_digest")
        if not isinstance(self.authority_provenance, EvaluatorProvenance):
            raise TypeError("causal obligation authority_provenance must be EvaluatorProvenance")
        if self.evidence_digest not in self.authority_provenance.output_evidence_refs:
            raise FrontierAssuranceError(
                "causal evidence must be referenced by obligation authority"
            )
        if not isinstance(self.severity, ObligationSeverity):
            raise TypeError("causal obligation severity must be ObligationSeverity")
        if not self.premise_ids or not self.consequence_ids:
            raise FrontierAssuranceError("causal obligation requires premises and consequences")
        if len(set(self.premise_ids)) != len(self.premise_ids):
            raise FrontierAssuranceError("causal premise ids must be unique")
        if len(set(self.consequence_ids)) != len(self.consequence_ids):
            raise FrontierAssuranceError("causal consequence ids must be unique")
        if self.resolved != (self.resolution_digest is not None):
            raise FrontierAssuranceError("resolved state and resolution digest must agree")
        if self.resolved:
            if not isinstance(self.resolution_authority, EvaluatorProvenance):
                raise TypeError("resolved causal obligation requires resolution authority")
            if self.resolution_digest not in self.resolution_authority.output_evidence_refs:
                raise FrontierAssuranceError(
                    "causal resolution evidence must be referenced by resolution authority"
                )
            if (
                self.severity is ObligationSeverity.CRITICAL
                and self.resolution_authority.evaluator_id
                == self.authority_provenance.evaluator_id
            ):
                raise FrontierAssuranceError(
                    "critical causal resolution requires independent authority"
                )
        elif self.resolution_authority is not None:
            raise FrontierAssuranceError(
                "unresolved causal obligation cannot carry resolution authority"
            )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "consequence_ids": self.consequence_ids,
                "authority_provenance_digest": self.authority_provenance.digest,
                "evidence_digest": self.evidence_digest,
                "obligation_id": self.obligation_id,
                "premise_ids": self.premise_ids,
                "resolution_digest": self.resolution_digest,
                "resolution_authority_digest": (
                    self.resolution_authority.digest
                    if self.resolution_authority is not None
                    else None
                ),
                "resolved": self.resolved,
                "severity": int(self.severity),
            }
        )


class CausalProofLedger:
    """Tracks unresolved setup/payoff and cause/effect obligations."""

    def __init__(self) -> None:
        self._items: dict[str, CausalObligation] = {}

    def add(self, item: CausalObligation) -> None:
        if item.obligation_id in self._items:
            raise FrontierAssuranceError("duplicate causal obligation")
        self._items[item.obligation_id] = item

    def resolve(
        self,
        obligation_id: str,
        resolution_digest: str,
        *,
        resolution_authority: EvaluatorProvenance,
    ) -> None:
        item = self._items.get(obligation_id)
        if item is None:
            raise FrontierAssuranceError("unknown causal obligation")
        digest = _stable(resolution_digest, "resolution_digest")
        self._items[obligation_id] = CausalObligation(
            obligation_id=item.obligation_id,
            premise_ids=item.premise_ids,
            consequence_ids=item.consequence_ids,
            evidence_digest=item.evidence_digest,
            authority_provenance=item.authority_provenance,
            severity=item.severity,
            resolved=True,
            resolution_digest=digest,
            resolution_authority=resolution_authority,
        )

    def blockers_for(self, changed_ids: Iterable[str]) -> tuple[CausalObligation, ...]:
        changed = set(changed_ids)
        blockers = [
            item
            for item in self._items.values()
            if not item.resolved
            and changed.intersection(set(item.premise_ids) | set(item.consequence_ids))
        ]
        return tuple(sorted(blockers, key=lambda item: (-int(item.severity), item.obligation_id)))

    @property
    def digest(self) -> str:
        return canonical_digest(
            [
                (item.obligation_id, item.digest)
                for item in sorted(self._items.values(), key=lambda row: row.obligation_id)
            ]
        )


@dataclass(frozen=True, slots=True)
class HorizonProbe:
    probe_id: str
    anchor_id: str
    distant_ids: tuple[str, ...]
    minimum_distance: int
    evidence_digest: str
    evaluator_provenance: EvaluatorProvenance
    passed: bool

    def __post_init__(self) -> None:
        _stable(self.probe_id, "probe_id")
        _stable(self.anchor_id, "anchor_id")
        _stable(self.evidence_digest, "evidence_digest")
        if not isinstance(self.evaluator_provenance, EvaluatorProvenance):
            raise TypeError("horizon probe evaluator_provenance must be EvaluatorProvenance")
        if self.evidence_digest not in self.evaluator_provenance.output_evidence_refs:
            raise FrontierAssuranceError(
                "horizon evidence must be referenced by evaluator authority"
            )
        if not isinstance(self.passed, bool):
            raise TypeError("horizon probe passed state must be boolean")
        if self.minimum_distance < 1:
            raise FrontierAssuranceError("minimum_distance must be positive")
        if not self.distant_ids:
            raise FrontierAssuranceError("horizon probe requires distant ids")


class HorizonConsistencySentinel:
    """Requires consistency evidence at multiple narrative/gameplay horizons."""

    def __init__(self, required_horizons: Sequence[int] = (1, 10, 100)) -> None:
        horizons = tuple(int(x) for x in required_horizons)
        if not horizons or any(x < 1 for x in horizons):
            raise FrontierAssuranceError("required horizons must be positive")
        if tuple(sorted(set(horizons))) != horizons:
            raise FrontierAssuranceError("required horizons must be unique and ordered")
        self.required_horizons = horizons
        self._probes: dict[str, HorizonProbe] = {}

    def record(self, probe: HorizonProbe) -> None:
        if probe.probe_id in self._probes:
            raise FrontierAssuranceError("duplicate horizon probe")
        self._probes[probe.probe_id] = probe

    def qualified(self, anchor_id: str) -> bool:
        covered = {
            horizon
            for horizon in self.required_horizons
            if any(
                row.anchor_id == anchor_id
                and row.passed
                and row.minimum_distance >= horizon
                for row in self._probes.values()
            )
        }
        return covered == set(self.required_horizons)


@dataclass(frozen=True, slots=True)
class EffortSignal:
    risk: float
    uncertainty: float
    blast_radius: float
    novelty: float
    marginal_gain: float

    def __post_init__(self) -> None:
        for label in ("risk", "uncertainty", "blast_radius", "novelty", "marginal_gain"):
            object.__setattr__(self, label, _unit(getattr(self, label), label))


@dataclass(frozen=True, slots=True)
class EffortDecision:
    mode: EffortMode
    score: float
    reason_digest: str


class EffortPortfolioScheduler:
    """Chooses an exact forge tier without changing tier semantics."""

    def __init__(self, *, medium_threshold: float = 0.42, extreme_threshold: float = 0.72) -> None:
        self.medium_threshold = _unit(medium_threshold, "medium_threshold")
        self.extreme_threshold = _unit(extreme_threshold, "extreme_threshold")
        if self.medium_threshold >= self.extreme_threshold:
            raise FrontierAssuranceError("effort thresholds must be increasing")

    def choose(self, signal: EffortSignal) -> EffortDecision:
        # Risk and blast radius dominate; novelty/marginal gain justify deeper search
        # without allowing a low-risk vanity task to consume 10k rounds.
        score = (
            0.30 * signal.risk
            + 0.25 * signal.uncertainty
            + 0.25 * signal.blast_radius
            + 0.10 * signal.novelty
            + 0.10 * signal.marginal_gain
        )
        if score >= self.extreme_threshold:
            mode = EffortMode.FORGE_10000
        elif score >= self.medium_threshold:
            mode = EffortMode.FORGE_1000
        else:
            mode = EffortMode.FORGE_100
        return EffortDecision(
            mode=mode,
            score=score,
            reason_digest=canonical_digest(
                {
                    "mode": int(mode),
                    "score": score,
                    "signal": {
                        "blast_radius": signal.blast_radius,
                        "marginal_gain": signal.marginal_gain,
                        "novelty": signal.novelty,
                        "risk": signal.risk,
                        "uncertainty": signal.uncertainty,
                    },
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class GenealogyNode:
    candidate_digest: str
    parent_digests: tuple[str, ...]
    mutation_digest: str
    round_index: int
    mutation_authority: EvaluatorProvenance
    mutation_evidence_digest: str

    def __post_init__(self) -> None:
        _stable(self.candidate_digest, "candidate_digest")
        _stable(self.mutation_digest, "mutation_digest")
        _stable(self.mutation_evidence_digest, "mutation_evidence_digest")
        if isinstance(self.round_index, bool) or not isinstance(self.round_index, int):
            raise TypeError("round_index must be an integer")
        if self.round_index < 0:
            raise FrontierAssuranceError("round_index must be non-negative")
        if not isinstance(self.mutation_authority, EvaluatorProvenance):
            raise TypeError("genealogy mutation_authority must be EvaluatorProvenance")
        if self.mutation_evidence_digest not in self.mutation_authority.output_evidence_refs:
            raise FrontierAssuranceError(
                "genealogy mutation evidence must be referenced by mutation authority"
            )
        if len(self.parent_digests) != len(set(self.parent_digests)):
            raise FrontierAssuranceError("genealogy parent digests must be unique")
        for parent in self.parent_digests:
            _stable(parent, "parent_digest")
        if self.candidate_digest in self.parent_digests:
            raise FrontierAssuranceError("candidate cannot parent itself")

    @property
    def mutation_binding_digest(self) -> str:
        return canonical_digest(
            {
                "candidate_digest": self.candidate_digest,
                "mutation_authority_digest": self.mutation_authority.digest,
                "mutation_digest": self.mutation_digest,
                "mutation_evidence_digest": self.mutation_evidence_digest,
                "parent_digests": list(self.parent_digests),
                "round_index": self.round_index,
            }
        )


class ArtifactGenealogy:
    """Maintains candidate ancestry and rejects cycles or unknown parents."""

    def __init__(self) -> None:
        self._nodes: dict[str, GenealogyNode] = {}

    def add(self, node: GenealogyNode, *, allow_root: bool = False) -> None:
        if node.candidate_digest in self._nodes:
            raise FrontierAssuranceError("duplicate genealogy candidate")
        missing = [parent for parent in node.parent_digests if parent not in self._nodes]
        if missing:
            raise FrontierAssuranceError(f"unknown genealogy parents: {sorted(missing)}")
        if not node.parent_digests and not allow_root and self._nodes:
            raise FrontierAssuranceError("non-initial genealogy node requires a parent")
        self._nodes[node.candidate_digest] = node

    def ancestors(self, candidate_digest: str) -> tuple[str, ...]:
        if candidate_digest not in self._nodes:
            raise FrontierAssuranceError("unknown genealogy candidate")
        seen: set[str] = set()
        stack = list(self._nodes[candidate_digest].parent_digests)
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self._nodes[current].parent_digests)
        return tuple(sorted(seen))

    @property
    def digest(self) -> str:
        return canonical_digest(
            [
                {
                    "candidate_digest": row.candidate_digest,
                    "mutation_binding_digest": row.mutation_binding_digest,
                }
                for row in sorted(
                    self._nodes.values(),
                    key=lambda item: item.candidate_digest,
                )
            ]
        )


class EvaluatorIndependenceGraph:
    """Rejects judge quorums whose apparent diversity shares one dependency root."""

    def __init__(self) -> None:
        self._roots: dict[str, frozenset[str]] = {}

    def register(self, evaluator_id: str, independence_roots: Iterable[str]) -> None:
        evaluator = _stable(evaluator_id, "evaluator_id")
        roots = frozenset(_stable(x, "independence_root") for x in independence_roots)
        if not roots:
            raise FrontierAssuranceError("evaluator requires at least one independence root")
        if evaluator in self._roots:
            raise FrontierAssuranceError("duplicate evaluator")
        self._roots[evaluator] = roots

    def independent_groups(self, evaluator_ids: Iterable[str]) -> tuple[frozenset[str], ...]:
        ids = tuple(evaluator_ids)
        unknown = [e for e in ids if e not in self._roots]
        if unknown:
            raise FrontierAssuranceError(f"unknown evaluators: {sorted(unknown)}")
        groups: list[set[str]] = []
        for evaluator in ids:
            roots = set(self._roots[evaluator])
            touching = [group for group in groups if group.intersection(roots)]
            if not touching:
                groups.append(roots)
                continue
            merged = set(roots)
            for group in touching:
                merged.update(group)
                groups.remove(group)
            groups.append(merged)
        return tuple(frozenset(group) for group in groups)

    def quorum_is_independent(self, evaluator_ids: Iterable[str], minimum_groups: int = 3) -> bool:
        if minimum_groups < 1:
            raise FrontierAssuranceError("minimum_groups must be positive")
        return len(self.independent_groups(evaluator_ids)) >= minimum_groups


@dataclass(frozen=True, slots=True)
class RegretObservation:
    policy_id: str
    champion_score: float
    alternative_score: float
    weight: float = 1.0

    def __post_init__(self) -> None:
        _stable(self.policy_id, "policy_id")
        object.__setattr__(self, "champion_score", _unit(self.champion_score, "champion_score"))
        object.__setattr__(self, "alternative_score", _unit(self.alternative_score, "alternative_score"))
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)) or self.weight <= 0:
            raise FrontierAssuranceError("weight must be positive")


class RegretLedger:
    """Tracks counterfactual regret so one preferred player policy cannot dominate."""

    def __init__(self, maximum_weighted_regret: float = 0.08) -> None:
        self.maximum_weighted_regret = _unit(maximum_weighted_regret, "maximum_weighted_regret")
        self._rows: dict[str, RegretObservation] = {}

    def record(self, row: RegretObservation) -> None:
        if row.policy_id in self._rows:
            raise FrontierAssuranceError("duplicate regret policy")
        self._rows[row.policy_id] = row

    @property
    def weighted_regret(self) -> float:
        if not self._rows:
            return 0.0
        total_weight = sum(float(row.weight) for row in self._rows.values())
        return sum(
            max(0.0, row.alternative_score - row.champion_score) * float(row.weight)
            for row in self._rows.values()
        ) / total_weight

    def promotion_allowed(self) -> bool:
        return bool(self._rows) and self.weighted_regret <= self.maximum_weighted_regret


@dataclass(frozen=True, slots=True)
class EvidenceInvalidationReceipt:
    node_id: str
    affected_ids: tuple[str, ...]
    authority_provenance: EvaluatorProvenance
    evidence_digest: str
    receipt_digest: str

    def __post_init__(self) -> None:
        _stable(self.node_id, "node_id")
        _stable(self.evidence_digest, "evidence_digest")
        if not isinstance(self.authority_provenance, EvaluatorProvenance):
            raise TypeError("invalidation authority_provenance must be EvaluatorProvenance")
        if self.evidence_digest not in self.authority_provenance.output_evidence_refs:
            raise FrontierAssuranceError(
                "invalidation evidence must be referenced by invalidation authority"
            )
        if not self.affected_ids or self.node_id not in self.affected_ids:
            raise FrontierAssuranceError(
                "invalidation receipt must include the invalidated source node"
            )
        if tuple(sorted(set(self.affected_ids))) != self.affected_ids:
            raise FrontierAssuranceError(
                "invalidation affected ids must be unique canonical order"
            )
        if self.receipt_digest != canonical_digest(self.payload()):
            raise FrontierAssuranceError("invalidation receipt digest mismatch")

    def payload(self) -> dict[str, object]:
        return {
            "affected_ids": list(self.affected_ids),
            "authority_provenance_digest": self.authority_provenance.digest,
            "evidence_digest": self.evidence_digest,
            "node_id": self.node_id,
        }


class EvidenceInvalidationGraph:
    """Propagates attributed source/evidence drift into dependent qualifications."""

    def __init__(self) -> None:
        self._deps: dict[str, set[str]] = {}
        self._reverse: dict[str, set[str]] = {}
        self._invalid: set[str] = set()

    def add(self, node_id: str, *, depends_on: Iterable[str] = ()) -> None:
        node = _stable(node_id, "node_id")
        if node in self._deps:
            raise FrontierAssuranceError("duplicate evidence node")
        parents = {_stable(x, "dependency") for x in depends_on}
        missing = parents - set(self._deps)
        if missing:
            raise FrontierAssuranceError(f"unknown evidence dependencies: {sorted(missing)}")
        self._deps[node] = parents
        self._reverse.setdefault(node, set())
        for parent in parents:
            self._reverse.setdefault(parent, set()).add(node)

    def invalidate(
        self,
        node_id: str,
        *,
        authority_provenance: EvaluatorProvenance,
        evidence_digest: str,
    ) -> EvidenceInvalidationReceipt:
        node = _stable(node_id, "node_id")
        if node not in self._deps:
            raise FrontierAssuranceError("unknown evidence node")
        if not isinstance(authority_provenance, EvaluatorProvenance):
            raise TypeError("invalidation authority_provenance must be EvaluatorProvenance")
        _stable(evidence_digest, "evidence_digest")
        if evidence_digest not in authority_provenance.output_evidence_refs:
            raise FrontierAssuranceError(
                "invalidation evidence must be referenced by invalidation authority"
            )
        affected: set[str] = set()
        stack = [node]
        while stack:
            current = stack.pop()
            if current in affected:
                continue
            affected.add(current)
            stack.extend(self._reverse.get(current, ()))
        affected_ids = tuple(sorted(affected))
        self._invalid.update(affected)
        payload = {
            "affected_ids": list(affected_ids),
            "authority_provenance_digest": authority_provenance.digest,
            "evidence_digest": evidence_digest,
            "node_id": node,
        }
        return EvidenceInvalidationReceipt(
            node_id=node,
            affected_ids=affected_ids,
            authority_provenance=authority_provenance,
            evidence_digest=evidence_digest,
            receipt_digest=canonical_digest(payload),
        )

    def is_valid(self, node_id: str) -> bool:
        if node_id not in self._deps:
            raise FrontierAssuranceError("unknown evidence node")
        return node_id not in self._invalid


class ConvergenceMonitor:
    """Detects cycling and quality stagnation without forcing premature success."""

    def __init__(self, *, window: int = 12, minimum_gain: float = 0.002) -> None:
        if window < 4:
            raise FrontierAssuranceError("convergence window must be at least four")
        self.window = int(window)
        self.minimum_gain = _unit(minimum_gain, "minimum_gain")
        self._history: list[tuple[str, float]] = []

    def record(self, champion_digest: str, aggregate_quality: float) -> None:
        self._history.append(
            (_stable(champion_digest, "champion_digest"), _unit(aggregate_quality, "aggregate_quality"))
        )

    @property
    def cycling(self) -> bool:
        recent = self._history[-self.window :]
        if len(recent) < self.window:
            return False
        digests = [row[0] for row in recent]
        return len(set(digests)) <= max(2, self.window // 4)

    @property
    def stagnant(self) -> bool:
        recent = self._history[-self.window :]
        if len(recent) < self.window:
            return False
        qualities = [row[1] for row in recent]
        return max(qualities) - min(qualities) < self.minimum_gain

    @property
    def requires_hypothesis_injection(self) -> bool:
        return self.cycling or self.stagnant


@dataclass(frozen=True, slots=True)
class WisdomRecord:
    lesson_id: str
    scope_ids: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    statement_digest: str
    evidence_authority: EvaluatorProvenance
    independently_verified: bool
    verification_evidence_digest: str | None = None
    verifier_provenance: EvaluatorProvenance | None = None

    def __post_init__(self) -> None:
        _stable(self.lesson_id, "lesson_id")
        _stable(self.statement_digest, "statement_digest")
        if not isinstance(self.evidence_authority, EvaluatorProvenance):
            raise TypeError("wisdom evidence_authority must be EvaluatorProvenance")
        if not isinstance(self.independently_verified, bool):
            raise TypeError("wisdom independent verification state must be boolean")
        if not self.scope_ids or not self.evidence_digests:
            raise FrontierAssuranceError("wisdom record requires scope and evidence")
        if set(self.evidence_digests) - set(self.evidence_authority.output_evidence_refs):
            raise FrontierAssuranceError(
                "wisdom evidence must be referenced by evidence authority"
            )
        if self.independently_verified:
            if not isinstance(self.verifier_provenance, EvaluatorProvenance):
                raise TypeError("verified wisdom requires verifier provenance")
            if (
                not isinstance(self.verification_evidence_digest, str)
                or len(self.verification_evidence_digest.strip()) < 8
            ):
                raise FrontierAssuranceError(
                    "verified wisdom requires stable verification evidence"
                )
            if self.verification_evidence_digest not in self.verifier_provenance.output_evidence_refs:
                raise FrontierAssuranceError(
                    "wisdom verification evidence must be referenced by verifier authority"
                )
            if self.verifier_provenance.evaluator_id == self.evidence_authority.evaluator_id:
                raise FrontierAssuranceError(
                    "wisdom verification requires independent authority"
                )
        elif self.verification_evidence_digest is not None or self.verifier_provenance is not None:
            raise FrontierAssuranceError(
                "unverified wisdom cannot carry verifier authority state"
            )

    @property
    def evidence_binding_digest(self) -> str:
        return canonical_digest(
            {
                "evidence_authority_digest": self.evidence_authority.digest,
                "evidence_digests": list(self.evidence_digests),
                "lesson_id": self.lesson_id,
                "scope_ids": list(self.scope_ids),
                "statement_digest": self.statement_digest,
                "verification_evidence_digest": self.verification_evidence_digest,
                "verifier_provenance_digest": (
                    self.verifier_provenance.digest
                    if self.verifier_provenance is not None
                    else None
                ),
            }
        )


class ProjectWisdomLedger:
    """Stores only evidence-backed project lessons; candidates remain sandboxed."""

    def __init__(self) -> None:
        self._records: dict[str, WisdomRecord] = {}

    def promote(self, record: WisdomRecord) -> None:
        if not record.independently_verified:
            raise FrontierAssuranceError("project wisdom requires independent verification")
        if record.lesson_id in self._records:
            raise FrontierAssuranceError("duplicate project wisdom lesson")
        self._records[record.lesson_id] = record

    def applicable(self, scope_id: str) -> tuple[WisdomRecord, ...]:
        return tuple(
            sorted(
                (row for row in self._records.values() if scope_id in row.scope_ids),
                key=lambda row: row.lesson_id,
            )
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            [
                {
                    "evidence_digests": row.evidence_digests,
                    "evidence_binding_digest": row.evidence_binding_digest,
                    "evidence_authority_digest": row.evidence_authority.digest,
                    "lesson_id": row.lesson_id,
                    "scope_ids": row.scope_ids,
                    "statement_digest": row.statement_digest,
                    "verification_evidence_digest": row.verification_evidence_digest,
                    "verifier_provenance_digest": (
                        row.verifier_provenance.digest
                        if row.verifier_provenance is not None
                        else None
                    ),
                }
                for row in sorted(self._records.values(), key=lambda value: value.lesson_id)
            ]
        )
