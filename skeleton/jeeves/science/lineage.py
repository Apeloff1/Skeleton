"""Chronological scientific lineage and evidence-gated architecture promotion.

Jeeves should not suffer from recency bias.  A technique enters the active
architecture because it improves an explicitly measured frontier while
preserving non-negotiable invariants, not because its publication year is
larger.  This module records the intellectual lineage and provides a small,
deterministic promotion protocol that can be reused by compiler, planner,
memory, control, and learning subsystems.

The built-in registry is intentionally a curated *engineering lineage*, not a
claim to enumerate all scientific work.  Each record says which idea Jeeves
retains, what assumptions accompany it, and which failure modes remain.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple


class LineageDomain(str, Enum):
    COMPUTATION = "computation"
    INFORMATION = "information"
    DECISION = "decision"
    CONTROL = "control"
    SEARCH = "search"
    VERIFICATION = "verification"
    PROGRAM_ANALYSIS = "program_analysis"
    COMPILERS = "compilers"
    DECOMPILATION = "decompilation"
    PROBABILITY = "probability"
    CAUSALITY = "causality"
    REINFORCEMENT_LEARNING = "reinforcement_learning"
    PLANNING = "planning"
    METAREASONING = "metareasoning"
    REPRESENTATION = "representation"


class EvidenceGrade(str, Enum):
    FOUNDATIONAL = "foundational"
    FORMALLY_VERIFIED = "formally_verified"
    REPLICATED = "replicated"
    EMPIRICAL = "empirical"
    EMERGING = "emerging"
    HYPOTHESIS = "hypothesis"


class PromotionStatus(str, Enum):
    PROMOTE = "promote"
    SHADOW = "shadow"
    RETAIN_BASELINE = "retain_baseline"
    REJECT = "reject"


@dataclass(frozen=True)
class TheoryRecord:
    """One scientific or engineering contribution relevant to the runtime."""

    theory_id: str
    year: int
    title: str
    domain: LineageDomain
    retained_principle: str
    evidence_grade: EvidenceGrade
    sources: Tuple[str, ...] = ()
    assumptions: Tuple[str, ...] = ()
    guarantees: Tuple[str, ...] = ()
    failure_modes: Tuple[str, ...] = ()
    extends: Tuple[str, ...] = ()
    supersedes: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.theory_id.strip():
            raise ValueError("theory_id must be non-empty")
        if self.year < 1800 or self.year > 3000:
            raise ValueError("year is outside the supported lineage range")
        if not self.title.strip() or not self.retained_principle.strip():
            raise ValueError("title and retained_principle must be non-empty")

    def as_json(self) -> Mapping[str, object]:
        return {
            "theory_id": self.theory_id,
            "year": self.year,
            "title": self.title,
            "domain": self.domain.value,
            "retained_principle": self.retained_principle,
            "evidence_grade": self.evidence_grade.value,
            "sources": list(self.sources),
            "assumptions": list(self.assumptions),
            "guarantees": list(self.guarantees),
            "failure_modes": list(self.failure_modes),
            "extends": list(self.extends),
            "supersedes": list(self.supersedes),
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class PromotionCriterion:
    """A normalized objective used when comparing an incumbent and candidate."""

    name: str
    weight: float = 1.0
    minimum_candidate: float = 0.0
    maximum_regression: float = 0.0
    mandatory: bool = False
    higher_is_better: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("criterion name must be non-empty")
        if self.weight < 0.0:
            raise ValueError("criterion weight cannot be negative")
        if self.maximum_regression < 0.0:
            raise ValueError("maximum_regression cannot be negative")

    def normalize(self, value: float) -> float:
        return float(value) if self.higher_is_better else -float(value)


@dataclass(frozen=True)
class PromotionDecision:
    status: PromotionStatus
    incumbent_id: str
    candidate_id: str
    weighted_delta: float
    mandatory_failures: Tuple[str, ...]
    insufficient_evidence: Tuple[str, ...]
    regressions: Tuple[str, ...]
    improvements: Tuple[str, ...]
    rationale: Tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class ArchitectureObservation:
    """Measured result for one architecture under one reproducible evaluation."""

    architecture_id: str
    metrics: Mapping[str, float]
    evidence_count: int
    independent_runs: int
    verified: bool = False
    adversarially_tested: bool = False
    reproduction_id: str = ""

    def __post_init__(self) -> None:
        if not self.architecture_id:
            raise ValueError("architecture_id must be non-empty")
        if self.evidence_count < 0 or self.independent_runs < 0:
            raise ValueError("evidence counters cannot be negative")
        for key, value in self.metrics.items():
            if not key:
                raise ValueError("metric names must be non-empty")
            numeric = float(value)
            if numeric != numeric or numeric in (float("inf"), float("-inf")):
                raise ValueError("metrics must be finite")


class ArchitecturalLineage:
    """Append-only theory registry plus conservative promotion protocol."""

    def __init__(self, records: Iterable[TheoryRecord] = ()) -> None:
        self._records: Dict[str, TheoryRecord] = {}
        for record in records:
            self.register(record)

    def register(self, record: TheoryRecord) -> None:
        existing = self._records.get(record.theory_id)
        if existing is not None and existing != record:
            raise ValueError("theory_id already registered with different content")
        unknown = [
            parent
            for parent in record.extends + record.supersedes
            if parent not in self._records
        ]
        if unknown:
            raise ValueError("lineage references unknown predecessor(s): %s" % ", ".join(unknown))
        self._records[record.theory_id] = record

    def get(self, theory_id: str) -> TheoryRecord:
        return self._records[theory_id]

    def ordered(
        self,
        *,
        domain: Optional[LineageDomain] = None,
        through_year: Optional[int] = None,
    ) -> Tuple[TheoryRecord, ...]:
        records = self._records.values()
        filtered = [
            record
            for record in records
            if (domain is None or record.domain == domain)
            and (through_year is None or record.year <= through_year)
        ]
        return tuple(sorted(filtered, key=lambda item: (item.year, item.theory_id)))

    def frontier_at(self, year: int) -> Mapping[LineageDomain, Tuple[TheoryRecord, ...]]:
        """Return non-superseded records known by ``year`` for each domain.

        Supersession is deliberately local and explicit.  A newer record does
        not erase an older one simply because both share a domain.
        """

        available = self.ordered(through_year=year)
        superseded = {
            predecessor
            for record in available
            for predecessor in record.supersedes
        }
        result: Dict[LineageDomain, list[TheoryRecord]] = {}
        for record in available:
            if record.theory_id in superseded:
                continue
            result.setdefault(record.domain, []).append(record)
        return {
            domain: tuple(records)
            for domain, records in sorted(result.items(), key=lambda item: item[0].value)
        }

    def lineage_path(self, theory_id: str) -> Tuple[TheoryRecord, ...]:
        """Return all transitive predecessors in chronological order."""

        seen = set()

        def walk(current: str) -> None:
            if current in seen:
                return
            seen.add(current)
            record = self.get(current)
            for parent in record.extends + record.supersedes:
                walk(parent)

        walk(theory_id)
        return tuple(sorted((self.get(item) for item in seen), key=lambda item: (item.year, item.theory_id)))

    def evaluate_promotion(
        self,
        *,
        incumbent: ArchitectureObservation,
        candidate: ArchitectureObservation,
        criteria: Sequence[PromotionCriterion],
        minimum_evidence: int = 3,
        minimum_independent_runs: int = 2,
        require_verification: bool = False,
        require_adversarial_test: bool = False,
        minimum_weighted_delta: float = 0.0,
    ) -> PromotionDecision:
        """Compare a candidate without recency bias.

        Mandatory criteria are hard gates.  Non-mandatory criteria form a
        weighted utility difference, but any regression beyond the declared
        tolerance sends the candidate to shadow evaluation instead of silently
        accepting a tradeoff.
        """

        if candidate.evidence_count < minimum_evidence:
            evidence = ("evidence_count",)
        else:
            evidence = ()
        if candidate.independent_runs < minimum_independent_runs:
            evidence += ("independent_runs",)
        if require_verification and not candidate.verified:
            evidence += ("verification",)
        if require_adversarial_test and not candidate.adversarially_tested:
            evidence += ("adversarial_test",)

        mandatory_failures = []
        regressions = []
        improvements = []
        weighted_delta = 0.0
        total_weight = 0.0

        for criterion in criteria:
            if criterion.name not in incumbent.metrics or criterion.name not in candidate.metrics:
                if criterion.mandatory:
                    mandatory_failures.append(criterion.name + ":missing")
                continue
            old = criterion.normalize(incumbent.metrics[criterion.name])
            new = criterion.normalize(candidate.metrics[criterion.name])
            threshold = criterion.normalize(criterion.minimum_candidate)
            delta = new - old
            if criterion.mandatory and new < threshold:
                mandatory_failures.append(criterion.name + ":below_minimum")
            if delta < -criterion.maximum_regression:
                regressions.append(criterion.name)
                if criterion.mandatory:
                    mandatory_failures.append(criterion.name + ":regressed")
            elif delta > 0.0:
                improvements.append(criterion.name)
            weighted_delta += criterion.weight * delta
            total_weight += criterion.weight

        if total_weight:
            weighted_delta /= total_weight

        rationale = []
        if mandatory_failures:
            status = PromotionStatus.REJECT
            rationale.append("mandatory invariants failed")
        elif evidence:
            status = PromotionStatus.SHADOW
            rationale.append("candidate lacks promotion-grade evidence")
        elif regressions:
            status = PromotionStatus.SHADOW
            rationale.append("candidate regresses a guarded criterion")
        elif weighted_delta > minimum_weighted_delta:
            status = PromotionStatus.PROMOTE
            rationale.append("candidate improves the measured frontier without guarded regressions")
        else:
            status = PromotionStatus.RETAIN_BASELINE
            rationale.append("candidate did not demonstrate sufficient net improvement")

        payload = {
            "status": status.value,
            "incumbent": incumbent.architecture_id,
            "candidate": candidate.architecture_id,
            "weighted_delta": round(weighted_delta, 12),
            "mandatory_failures": sorted(set(mandatory_failures)),
            "insufficient_evidence": sorted(set(evidence)),
            "regressions": sorted(set(regressions)),
            "improvements": sorted(set(improvements)),
            "incumbent_reproduction": incumbent.reproduction_id,
            "candidate_reproduction": candidate.reproduction_id,
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return PromotionDecision(
            status=status,
            incumbent_id=incumbent.architecture_id,
            candidate_id=candidate.architecture_id,
            weighted_delta=weighted_delta,
            mandatory_failures=tuple(sorted(set(mandatory_failures))),
            insufficient_evidence=tuple(sorted(set(evidence))),
            regressions=tuple(sorted(set(regressions))),
            improvements=tuple(sorted(set(improvements))),
            rationale=tuple(rationale),
            fingerprint=fingerprint,
        )

    @property
    def fingerprint(self) -> str:
        payload = [record.as_json() for record in self.ordered()]
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()


def default_lineage() -> ArchitecturalLineage:
    """Build the curated lineage used to govern Jeeves architecture evolution."""

    records = [
        TheoryRecord(
            "turing_1936",
            1936,
            "Computable numbers and universal computation",
            LineageDomain.COMPUTATION,
            "Separate what is computable in principle from implementation strategy.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Turing, Proc. London Math. Soc. 1936",),
            guarantees=("formal model of effective computation",),
            failure_modes=("computability does not imply tractability",),
        ),
        TheoryRecord(
            "shannon_1948",
            1948,
            "A mathematical theory of communication",
            LineageDomain.INFORMATION,
            "Measure uncertainty and information explicitly rather than using confidence rhetoric.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Shannon, Bell System Technical Journal 1948",),
            guarantees=("entropy and channel-capacity formalism",),
        ),
        TheoryRecord(
            "bellman_1957",
            1957,
            "Dynamic programming and the principle of optimality",
            LineageDomain.DECISION,
            "Exploit recursive optimal substructure when the state representation is Markov-sufficient.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Bellman, Dynamic Programming, Princeton 1957",),
            assumptions=("state captures decision-relevant history",),
            failure_modes=("state explosion",),
        ),
        TheoryRecord(
            "kalman_1960",
            1960,
            "Recursive linear state estimation",
            LineageDomain.CONTROL,
            "Maintain an explicit uncertainty-bearing state estimate instead of treating observations as state.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Kalman, ASME Journal of Basic Engineering 1960",),
            assumptions=("classical form assumes linear Gaussian dynamics",),
            failure_modes=("model mismatch and non-Gaussian dynamics",),
        ),
        TheoryRecord(
            "astar_1968",
            1968,
            "A formal basis for heuristic determination of minimum-cost paths",
            LineageDomain.SEARCH,
            "Use admissible lower bounds to trade search effort for guaranteed solution quality.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Hart, Nilsson, Raphael, IEEE SSC 1968",),
            guarantees=("optimality under standard admissibility/consistency conditions",),
            failure_modes=("memory growth",),
        ),
        TheoryRecord(
            "hoare_1969",
            1969,
            "An axiomatic basis for computer programming",
            LineageDomain.VERIFICATION,
            "Attach preconditions, postconditions, and invariants to transformations.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Hoare, CACM 1969",),
            guarantees=("compositional partial-correctness reasoning",),
        ),
        TheoryRecord(
            "strips_1971",
            1971,
            "STRIPS planning representation",
            LineageDomain.PLANNING,
            "Represent actions by explicit applicability conditions and state effects.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Fikes and Nilsson, AI 1971",),
            failure_modes=("limited expressiveness without extensions",),
        ),
        TheoryRecord(
            "abstract_interpretation_1977",
            1977,
            "Abstract interpretation",
            LineageDomain.PROGRAM_ANALYSIS,
            "Compute sound program properties over abstract domains and fixed points.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Cousot and Cousot, POPL 1977",),
            guarantees=("sound over-approximation when transfer/join rules are sound",),
            failure_modes=("precision-cost tradeoff and widening loss",),
            extends=("hoare_1969",),
        ),
        TheoryRecord(
            "bayesian_networks_1985",
            1985,
            "Bayesian networks",
            LineageDomain.PROBABILITY,
            "Factor joint uncertainty by conditional independence structure.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Pearl, Bayesian Networks era, 1980s",),
            failure_modes=("incorrect graph assumptions produce incorrect posteriors",),
        ),
        TheoryRecord(
            "td_learning_1988",
            1988,
            "Temporal-difference learning",
            LineageDomain.REINFORCEMENT_LEARNING,
            "Learn predictions from bootstrapped temporal error rather than waiting for terminal outcomes.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Sutton, Machine Learning 1988",),
            assumptions=("stochastic-approximation conditions for classical convergence results",),
        ),
        TheoryRecord(
            "q_learning_1989",
            1989,
            "Q-learning",
            LineageDomain.REINFORCEMENT_LEARNING,
            "Separate behavior from an off-policy optimal control target where assumptions permit.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Watkins, 1989; Watkins and Dayan, 1992",),
            extends=("td_learning_1988",),
            failure_modes=("function approximation/off-policy instability outside classical setting",),
        ),
        TheoryRecord(
            "ssa_1991",
            1991,
            "Static single assignment form",
            LineageDomain.COMPILERS,
            "Give values explicit single definitions so def-use and dataflow facts become first-class.",
            EvidenceGrade.REPLICATED,
            sources=("Cytron et al., ACM TOPLAS 1991",),
            guarantees=("explicit def-use representation",),
        ),
        TheoryRecord(
            "metareasoning_1991",
            1991,
            "Rational metareasoning and value of computation",
            LineageDomain.METAREASONING,
            "Reasoning itself is an action whose expected benefit must exceed its cost.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Russell and Wefald, Do the Right Thing, MIT Press 1991",),
            failure_modes=("meta-level value estimates may themselves be expensive",),
        ),
        TheoryRecord(
            "scm_1995",
            1995,
            "Structural causal models and intervention calculus",
            LineageDomain.CAUSALITY,
            "Do not confuse observation, intervention, and counterfactual claims.",
            EvidenceGrade.FOUNDATIONAL,
            sources=("Pearl, causal graphical models/do-calculus, 1990s",),
            extends=("bayesian_networks_1985",),
            assumptions=("identification depends on graph and causal assumptions",),
        ),
        TheoryRecord(
            "llvm_2004",
            2004,
            "LLVM typed intermediate representation architecture",
            LineageDomain.COMPILERS,
            "Use a stable, analyzable IR between source-specific and target-specific layers.",
            EvidenceGrade.REPLICATED,
            sources=("Lattner and Adve, CGO 2004",),
            extends=("ssa_1991",),
        ),
        TheoryRecord(
            "compcert_2006",
            2006,
            "Mechanically verified compiler architecture",
            LineageDomain.VERIFICATION,
            "Prefer machine-checked semantic preservation for transformations where the assurance cost is justified.",
            EvidenceGrade.FORMALLY_VERIFIED,
            sources=("Leroy, CompCert project",),
            extends=("hoare_1969",),
            guarantees=("proved semantic preservation for the supported compiler pipeline",),
        ),
        TheoryRecord(
            "uct_2006",
            2006,
            "Upper Confidence bounds applied to Trees",
            LineageDomain.SEARCH,
            "Allocate simulation budget by balancing exploitation and uncertainty-driven exploration.",
            EvidenceGrade.REPLICATED,
            sources=("Kocsis and Szepesvari, ECML 2006",),
            extends=("astar_1968",),
        ),
        TheoryRecord(
            "pomcp_2010",
            2010,
            "Monte-Carlo planning in large POMDPs",
            LineageDomain.PLANNING,
            "Plan in belief space using sampled simulations when explicit belief trees are intractable.",
            EvidenceGrade.REPLICATED,
            sources=("Silver and Veness, NeurIPS 2010",),
            extends=("uct_2006", "bayesian_networks_1985"),
            failure_modes=("simulation/model bias",),
        ),
        TheoryRecord(
            "deep_q_2015",
            2015,
            "Deep Q-learning with replay and target networks",
            LineageDomain.REINFORCEMENT_LEARNING,
            "Use representation learning only behind replay, evaluation, and stability controls.",
            EvidenceGrade.REPLICATED,
            sources=("Mnih et al., Nature 2015",),
            extends=("q_learning_1989",),
            failure_modes=("distribution shift, extrapolation, instability",),
        ),
        TheoryRecord(
            "egg_2021",
            2021,
            "Equality saturation with e-graphs",
            LineageDomain.COMPILERS,
            "Represent many equivalent rewrites simultaneously and delay irreversible optimization choice.",
            EvidenceGrade.REPLICATED,
            sources=("Willsey et al., POPL 2021",),
            extends=("llvm_2004",),
            failure_modes=("e-graph growth and extraction cost",),
        ),
        TheoryRecord(
            "mlir_2021",
            2021,
            "Multi-level intermediate representation",
            LineageDomain.COMPILERS,
            "Keep domain semantics explicit in extensible dialects and lower them through legality-checked conversions.",
            EvidenceGrade.REPLICATED,
            sources=("MLIR project and 2021 design publication",),
            extends=("llvm_2004",),
        ),
        TheoryRecord(
            "alive2_2021",
            2021,
            "Automatic translation validation for LLVM transformations",
            LineageDomain.VERIFICATION,
            "Validate each optimized artifact against its source semantics instead of trusting an optimizer globally.",
            EvidenceGrade.REPLICATED,
            sources=("Alive2, PLDI 2021",),
            extends=("llvm_2004", "compcert_2006"),
        ),
        TheoryRecord(
            "sailr_2024",
            2024,
            "Compiler-aware control-flow structuring for decompilation",
            LineageDomain.DECOMPILATION,
            "Recover source-like structure using compiler-aware evidence instead of optimizing for syntactic prettiness.",
            EvidenceGrade.EMPIRICAL,
            sources=("SAILR, USENIX Security 2024",),
            failure_modes=("binary optimizations can destroy source structure",),
        ),
        TheoryRecord(
            "trex_2025",
            2025,
            "Deductive behavior-capturing type reconstruction",
            LineageDomain.DECOMPILATION,
            "Represent types that explain binary behavior and expose unrecoverable source information rather than invent it.",
            EvidenceGrade.EMPIRICAL,
            sources=("TRex, USENIX Security 2025",),
            extends=("sailr_2024", "abstract_interpretation_1977"),
        ),
        TheoryRecord(
            "llvm22_2026",
            2026,
            "LLVM 22 compiler infrastructure",
            LineageDomain.COMPILERS,
            "Track current target semantics while preserving explicit IR verification and reproducible pass boundaries.",
            EvidenceGrade.REPLICATED,
            sources=("LLVM 22.1.x documentation, 2026",),
            extends=("llvm_2004", "mlir_2021", "alive2_2021"),
        ),
        TheoryRecord(
            "compcert318_2026",
            2026,
            "CompCert 3.18",
            LineageDomain.VERIFICATION,
            "Keep formal semantic preservation as the assurance reference point even when faster unverified paths coexist.",
            EvidenceGrade.FORMALLY_VERIFIED,
            sources=("CompCert 3.18, August 2026",),
            extends=("compcert_2006",),
        ),
        TheoryRecord(
            "recstruct_2026",
            2026,
            "Scalable nested structure recovery from stripped binaries",
            LineageDomain.DECOMPILATION,
            "Recover structural types from binary evidence with scalable symbolic analysis and explicit structural constraints.",
            EvidenceGrade.EMPIRICAL,
            sources=("RecStruct, USENIX Security 2026",),
            extends=("trex_2025",),
        ),
    ]
    return ArchitecturalLineage(records)
