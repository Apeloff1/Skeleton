from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _package(name: str, path: Path) -> None:
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    module.__package__ = name
    sys.modules[name] = module


def _load(name: str, relative: str) -> None:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_package("skeleton", ROOT / "skeleton")
_package("skeleton.ai", ROOT / "skeleton" / "ai")
_package("skeleton.ai.game_builder", ROOT / "skeleton" / "ai" / "game_builder")
_load("skeleton.ai.game_builder.contracts", "skeleton/ai/game_builder/contracts.py")
_load("skeleton.ai.game_builder.frontier_assurance", "skeleton/ai/game_builder/frontier_assurance.py")

from skeleton.ai.game_builder.contracts import (  # noqa: E402
    EffortMode,
    EvaluatorProvenance,
    canonical_digest,
)
from skeleton.ai.game_builder.frontier_assurance import (  # noqa: E402
    ArtifactGenealogy,
    CausalObligation,
    CausalProofLedger,
    ConvergenceMonitor,
    EffortPortfolioScheduler,
    EffortSignal,
    EvaluatorIndependenceGraph,
    EvidenceInvalidationGraph,
    FrontierAssuranceError,
    GenealogyNode,
    HorizonConsistencySentinel,
    HorizonProbe,
    ObligationSeverity,
    ProjectWisdomLedger,
    RegretLedger,
    RegretObservation,
    WisdomRecord,
)


def _authority(
    evaluator_id: str,
    *evidence_refs: str,
) -> EvaluatorProvenance:
    return EvaluatorProvenance(
        evaluator_id=evaluator_id,
        operation_id=f"operation:{evaluator_id}",
        execution_id=f"execution:{evaluator_id}",
        execution_identity_digest=canonical_digest({"execution": evaluator_id}),
        finalization_intent_digest=canonical_digest({"finalization": evaluator_id}),
        authority_kind="deterministic_control",
        authority_identity_digest=canonical_digest({"authority": evaluator_id}),
        method_id="frontier-assurance",
        source_revision=canonical_digest({"source": evaluator_id})[:40],
        output_evidence_refs=tuple(evidence_refs),
    )


def test_causal_obligation_blocks_dependent_change_until_resolved() -> None:
    ledger = CausalProofLedger()
    item = CausalObligation(
        obligation_id="OBL-setup-payoff",
        premise_ids=("scene.early.promise",),
        consequence_ids=("scene.final.payoff",),
        evidence_digest="evidence-" + "a" * 32,
        authority_provenance=_authority(
            "causal-authority",
            "evidence-" + "a" * 32,
        ),
        severity=ObligationSeverity.CRITICAL,
    )
    ledger.add(item)
    assert ledger.blockers_for(("scene.final.payoff",)) == (item,)
    before = ledger.digest
    ledger.resolve(
        "OBL-setup-payoff",
        "resolution-" + "b" * 32,
        resolution_authority=_authority(
            "causal-resolver",
            "resolution-" + "b" * 32,
        ),
    )
    assert ledger.blockers_for(("scene.final.payoff",)) == ()
    assert ledger.digest != before


def test_horizon_sentinel_requires_near_mid_and_far_evidence() -> None:
    sentinel = HorizonConsistencySentinel((1, 10, 100))
    sentinel.record(
        HorizonProbe(
            probe_id="probe-near",
            anchor_id="character.arc",
            distant_ids=("scene.2",),
            minimum_distance=1,
            evidence_digest="near-" + "a" * 32,
            evaluator_provenance=_authority(
                "probe-near-authority",
                "near-" + "a" * 32,
            ),
            passed=True,
        )
    )
    sentinel.record(
        HorizonProbe(
            probe_id="probe-mid",
            anchor_id="character.arc",
            distant_ids=("scene.20",),
            minimum_distance=10,
            evidence_digest="mid-" + "b" * 32,
            evaluator_provenance=_authority(
                "probe-mid-authority",
                "mid-" + "b" * 32,
            ),
            passed=True,
        )
    )
    assert not sentinel.qualified("character.arc")
    sentinel.record(
        HorizonProbe(
            probe_id="probe-far",
            anchor_id="character.arc",
            distant_ids=("ending",),
            minimum_distance=100,
            evidence_digest="far-" + "c" * 32,
            evaluator_provenance=_authority(
                "probe-far-authority",
                "far-" + "c" * 32,
            ),
            passed=True,
        )
    )
    assert sentinel.qualified("character.arc")


def test_horizon_probe_rejects_truthy_non_boolean_pass_state() -> None:
    with pytest.raises(TypeError, match="horizon probe passed state must be boolean"):
        HorizonProbe(
            probe_id="probe-malformed",
            anchor_id="character.arc",
            distant_ids=("ending",),
            minimum_distance=100,
            evidence_digest="far-" + "c" * 32,
            evaluator_provenance=_authority(
                "probe-malformed-authority",
                "far-" + "c" * 32,
            ),
            passed="false",
        )


def test_causal_obligation_rejects_unattributed_evidence() -> None:
    with pytest.raises(
        FrontierAssuranceError,
        match="referenced by obligation authority",
    ):
        CausalObligation(
            obligation_id="OBL-unbound",
            premise_ids=("scene.early.promise",),
            consequence_ids=("scene.final.payoff",),
            evidence_digest="evidence-" + "a" * 32,
            authority_provenance=_authority(
                "wrong-causal-authority",
                "other-evidence-" + "x" * 32,
            ),
        )


def test_critical_causal_obligation_requires_independent_resolution() -> None:
    ledger = CausalProofLedger()
    item = CausalObligation(
        obligation_id="OBL-critical",
        premise_ids=("scene.early.promise",),
        consequence_ids=("scene.final.payoff",),
        evidence_digest="evidence-" + "a" * 32,
        authority_provenance=_authority(
            "same-causal-authority",
            "evidence-" + "a" * 32,
        ),
        severity=ObligationSeverity.CRITICAL,
    )
    ledger.add(item)
    with pytest.raises(
        FrontierAssuranceError,
        match="critical causal resolution requires independent authority",
    ):
        ledger.resolve(
            "OBL-critical",
            "resolution-" + "b" * 32,
            resolution_authority=_authority(
                "same-causal-authority",
                "resolution-" + "b" * 32,
            ),
        )


def test_horizon_probe_rejects_unattributed_evidence() -> None:
    with pytest.raises(
        FrontierAssuranceError,
        match="referenced by evaluator authority",
    ):
        HorizonProbe(
            probe_id="probe-unbound",
            anchor_id="character.arc",
            distant_ids=("ending",),
            minimum_distance=100,
            evidence_digest="far-" + "c" * 32,
            evaluator_provenance=_authority(
                "wrong-horizon-authority",
                "other-horizon-" + "x" * 32,
            ),
            passed=True,
        )


def test_effort_scheduler_selects_exact_supported_tiers() -> None:
    scheduler = EffortPortfolioScheduler(medium_threshold=0.4, extreme_threshold=0.7)
    low = scheduler.choose(EffortSignal(0.1, 0.1, 0.1, 0.2, 0.1))
    mid = scheduler.choose(EffortSignal(0.5, 0.5, 0.5, 0.2, 0.2))
    high = scheduler.choose(EffortSignal(0.95, 0.9, 0.95, 0.7, 0.7))
    assert low.mode is EffortMode.FORGE_100
    assert mid.mode is EffortMode.FORGE_1000
    assert high.mode is EffortMode.FORGE_10000
    assert len(low.reason_digest) == 64


def test_genealogy_requires_known_parents_and_recovers_ancestry() -> None:
    graph = ArtifactGenealogy()
    root_evidence = "mutation-root-evidence-" + "b" * 24
    root = GenealogyNode(
        candidate_digest="candidate-root-" + "a" * 24,
        parent_digests=(),
        mutation_digest="mutation-root-" + "b" * 24,
        round_index=0,
        mutation_authority=_authority("genealogy-root-authority", root_evidence),
        mutation_evidence_digest=root_evidence,
    )
    graph.add(root, allow_root=True)
    child_evidence = "mutation-child-evidence-" + "d" * 24
    child = GenealogyNode(
        candidate_digest="candidate-child-" + "c" * 24,
        parent_digests=(root.candidate_digest,),
        mutation_digest="mutation-child-" + "d" * 24,
        round_index=1,
        mutation_authority=_authority("genealogy-child-authority", child_evidence),
        mutation_evidence_digest=child_evidence,
    )
    graph.add(child)
    assert graph.ancestors(child.candidate_digest) == (root.candidate_digest,)
    with pytest.raises(FrontierAssuranceError, match="unknown genealogy parents"):
        graph.add(
            GenealogyNode(
                candidate_digest="candidate-bad-" + "e" * 24,
                parent_digests=("missing-parent-" + "f" * 24,),
                mutation_digest="mutation-bad-" + "1" * 24,
                round_index=2,
                mutation_authority=_authority(
                    "genealogy-bad-authority",
                    "mutation-bad-evidence-" + "1" * 24,
                ),
                mutation_evidence_digest="mutation-bad-evidence-" + "1" * 24,
            )
        )


def test_genealogy_rejects_unattributed_mutation_evidence() -> None:
    with pytest.raises(
        FrontierAssuranceError,
        match="referenced by mutation authority",
    ):
        GenealogyNode(
            candidate_digest="candidate-unbound-" + "a" * 24,
            parent_digests=(),
            mutation_digest="mutation-unbound-" + "b" * 24,
            round_index=0,
            mutation_authority=_authority(
                "wrong-genealogy-authority",
                "other-mutation-" + "x" * 24,
            ),
            mutation_evidence_digest="mutation-evidence-" + "e" * 24,
        )


def test_evaluator_independence_detects_correlated_quorum() -> None:
    graph = EvaluatorIndependenceGraph()
    graph.register("judge-alpha", ("provider-x", "method-sim"))
    graph.register("judge-beta", ("provider-x", "method-human"))
    graph.register("judge-charlie", ("provider-y", "method-formal"))
    graph.register("judge-delta", ("provider-z", "method-behavioral"))
    assert not graph.quorum_is_independent(
        ("judge-alpha", "judge-beta", "judge-charlie"),
        minimum_groups=3,
    )
    assert graph.quorum_is_independent(
        ("judge-alpha", "judge-charlie", "judge-delta"),
        minimum_groups=3,
    )


def test_regret_ledger_blocks_champion_that_hurts_alternate_player_policy() -> None:
    ledger = RegretLedger(maximum_weighted_regret=0.05)
    ledger.record(RegretObservation("novice-policy", champion_score=0.75, alternative_score=0.78, weight=2))
    ledger.record(RegretObservation("expert-policy", champion_score=0.8, alternative_score=0.81, weight=1))
    assert ledger.promotion_allowed()

    bad = RegretLedger(maximum_weighted_regret=0.05)
    bad.record(RegretObservation("novice-policy", champion_score=0.5, alternative_score=0.9, weight=1))
    assert bad.weighted_regret > 0.05
    assert not bad.promotion_allowed()


def test_evidence_invalidation_propagates_to_release_qualification() -> None:
    graph = EvidenceInvalidationGraph()
    graph.add("source.engine-doc")
    graph.add("mechanic.proof", depends_on=("source.engine-doc",))
    graph.add("family.GB17", depends_on=("mechanic.proof",))
    graph.add("release.gold", depends_on=("family.GB17",))
    invalidation_evidence = "invalidation-evidence-" + "e" * 24
    receipt = graph.invalidate(
        "source.engine-doc",
        authority_provenance=_authority(
            "evidence-invalidation-authority",
            invalidation_evidence,
        ),
        evidence_digest=invalidation_evidence,
    )
    assert receipt.affected_ids == (
        "family.GB17",
        "mechanic.proof",
        "release.gold",
        "source.engine-doc",
    )
    assert canonical_digest(receipt.payload()) == receipt.receipt_digest
    assert not graph.is_valid("release.gold")


def test_evidence_invalidation_requires_attributed_authority() -> None:
    graph = EvidenceInvalidationGraph()
    graph.add("source.engine-doc")
    evidence = "invalidation-evidence-" + "e" * 24
    with pytest.raises(
        FrontierAssuranceError,
        match="referenced by invalidation authority",
    ):
        graph.invalidate(
            "source.engine-doc",
            authority_provenance=_authority(
                "wrong-invalidation-authority",
                "other-invalidation-" + "x" * 24,
            ),
            evidence_digest=evidence,
        )


def test_convergence_monitor_detects_cycle_and_stagnation_without_declaring_success() -> None:
    monitor = ConvergenceMonitor(window=4, minimum_gain=0.01)
    for digest, score in (
        ("candidate-a-00000000", 0.80),
        ("candidate-b-00000000", 0.802),
        ("candidate-a-00000000", 0.801),
        ("candidate-b-00000000", 0.803),
    ):
        monitor.record(digest, score)
    assert monitor.cycling
    assert monitor.stagnant
    assert monitor.requires_hypothesis_injection


def test_project_wisdom_rejects_truthy_non_boolean_verification_state() -> None:
    with pytest.raises(TypeError, match="wisdom independent verification state must be boolean"):
        WisdomRecord(
            lesson_id="lesson-malformed",
            scope_ids=("GB09",),
            evidence_digests=("evidence-" + "a" * 32,),
            statement_digest="statement-" + "b" * 32,
            evidence_authority=_authority(
                "wisdom-malformed-authority",
                "evidence-" + "a" * 32,
            ),
            independently_verified="false",
        )


def test_project_wisdom_rejects_self_verification() -> None:
    with pytest.raises(
        FrontierAssuranceError,
        match="requires independent authority",
    ):
        WisdomRecord(
            lesson_id="lesson-self-verify",
            scope_ids=("GB09",),
            evidence_digests=("evidence-" + "a" * 32,),
            statement_digest="statement-" + "b" * 32,
            evidence_authority=_authority(
                "same-wisdom-authority",
                "evidence-" + "a" * 32,
                "wisdom-verify-" + "c" * 32,
            ),
            independently_verified=True,
            verification_evidence_digest="wisdom-verify-" + "c" * 32,
            verifier_provenance=_authority(
                "same-wisdom-authority",
                "wisdom-verify-" + "c" * 32,
            ),
        )


def test_project_wisdom_requires_independent_verification() -> None:
    ledger = ProjectWisdomLedger()
    pending = WisdomRecord(
        lesson_id="lesson-quest-001",
        scope_ids=("GB09", "quest.branching"),
        evidence_digests=("evidence-" + "a" * 32,),
        statement_digest="statement-" + "b" * 32,
        evidence_authority=_authority(
            "wisdom-authority",
            "evidence-" + "a" * 32,
        ),
        independently_verified=False,
    )
    with pytest.raises(FrontierAssuranceError, match="independent verification"):
        ledger.promote(pending)

    verified = WisdomRecord(
        lesson_id="lesson-quest-001",
        scope_ids=("GB09", "quest.branching"),
        evidence_digests=("evidence-" + "a" * 32,),
        statement_digest="statement-" + "b" * 32,
        evidence_authority=_authority(
            "wisdom-authority",
            "evidence-" + "a" * 32,
        ),
        independently_verified=True,
        verification_evidence_digest="wisdom-verify-" + "c" * 32,
        verifier_provenance=_authority(
            "wisdom-verifier",
            "wisdom-verify-" + "c" * 32,
        ),
    )
    ledger.promote(verified)
    assert ledger.applicable("GB09") == (verified,)
    assert len(ledger.digest) == 64
