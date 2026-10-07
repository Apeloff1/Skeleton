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
_load("skeleton.ai.game_builder.dual_rival_forge", "skeleton/ai/game_builder/dual_rival_forge.py")
_load("skeleton.ai.game_builder.evaluation", "skeleton/ai/game_builder/evaluation.py")
_load("skeleton.ai.game_builder.resource_governor", "skeleton/ai/game_builder/resource_governor.py")
_load("skeleton.ai.game_builder.quality_debt", "skeleton/ai/game_builder/quality_debt.py")
_load("skeleton.ai.game_builder.control_plane", "skeleton/ai/game_builder/control_plane.py")
_load("skeleton.ai.game_builder.resilience", "skeleton/ai/game_builder/resilience.py")
_load("skeleton.ai.game_builder.release", "skeleton/ai/game_builder/release.py")

from skeleton.ai.game_builder.contracts import (  # noqa: E402
    ArtifactIdentity,
    Candidate,
    Challenge,
    GateResult,
    QUALITY_AXES,
    Rival,
)
from skeleton.ai.game_builder.control_plane import ForgeControlPlane  # noqa: E402
from skeleton.ai.game_builder.dual_rival_forge import DualRivalForge  # noqa: E402
from skeleton.ai.game_builder.evaluation import (  # noqa: E402
    EvaluationError,
    EvaluationPanel,
    JudgeVerdict,
    blind_candidate_token,
)
from skeleton.ai.game_builder.quality_debt import (  # noqa: E402
    DebtItem,
    DebtSeverity,
    QualityDebtError,
    QualityDebtLedger,
)
from skeleton.ai.game_builder.resource_governor import (  # noqa: E402
    ResourceDelta,
    ResourceEnvelope,
    ResourceGovernor,
    ResourceLimitError,
)
from skeleton.ai.game_builder.resilience import (  # noqa: E402
    DissentLedger,
    ImpactGraph,
    Invariant,
    InvariantRegistry,
    NoveltyRecord,
    NoveltyReservoir,
    Objection,
    ResilienceError,
)
from skeleton.ai.game_builder.release import (  # noqa: E402
    FamilyQualification,
    GoldMasterBundle,
    GoldMasterTribunal,
    ReleaseArbitrationError,
    TribunalVote,
)


def _quality(value: float) -> dict[str, float]:
    return {axis: value for axis in QUALITY_AXES}


def _candidate(producer: str, token: str, quality: float) -> Candidate:
    suffix = (token * 40)[:40]
    return Candidate.create(
        producer_id=producer,
        artifact=ArtifactIdentity(
            artifact_digest=f"artifact-{suffix}",
            canon_digest=f"canon-{suffix}",
            provenance_digest=f"provenance-{suffix}",
            family_id="GB03",
            level_id="GBL-021",
        ),
        quality=_quality(quality),
        evidence_digests=(f"evidence-{suffix}",),
        assumption_digest=f"assumption-{suffix}",
    )


def _challenge(challenger: Rival, target: Candidate, token: str, quality: float) -> Challenge:
    improved = _candidate(challenger.value, token, quality)
    return Challenge(
        challenger_id=challenger.value,
        target_candidate_digest=target.digest,
        attack_digest=f"attack-{(token * 40)[:40]}",
        improved_candidate=improved,
        counterexample_digests=(f"counter-{(token * 40)[:40]}",),
    )


def _gates() -> tuple[GateResult, ...]:
    return (
        GateResult("rights", True, "rights-evidence-0000000000000000"),
        GateResult("continuity", True, "canon-evidence-00000000000000000"),
        GateResult("state", True, "state-evidence-000000000000000000"),
    )


def _panel(candidate: Candidate, value: float, *, spread: float = 0.0) -> tuple[EvaluationPanel, object]:
    panel = EvaluationPanel(
        ("judge-1", "judge-2", "judge-3"),
        minimum_quorum=3,
        minimum_method_diversity=2,
    )
    for index, evaluator in enumerate(panel.evaluator_ids):
        score = value + (spread if index == 2 else 0.0)
        panel.submit(
            JudgeVerdict.create(
                evaluator_id=evaluator,
                candidate_digest=candidate.digest,
                quality=_quality(score),
                confidence=0.9,
                evidence_digest=f"eval-{index}-0000000000000000000000000000",
                method_id="simulator" if index < 2 else "human-calibrated",
            )
        )
    return panel, panel.decide(candidate.digest)


def _resources() -> ResourceGovernor:
    return ResourceGovernor(
        ResourceEnvelope(
            max_tokens=1_000_000,
            max_tool_calls=10_000,
            max_artifact_bytes=100_000_000,
            max_retries=100,
            max_active_branches=16,
            max_concurrency=8,
            checkpoint_interval_rounds=10,
        )
    )


def test_panel_requires_three_independent_judges_and_multiple_methods() -> None:
    candidate = _candidate(Rival.A.value, "a", 0.5)
    panel = EvaluationPanel(("j1", "j2", "j3"))
    for evaluator in ("j1", "j2"):
        panel.submit(
            JudgeVerdict.create(
                evaluator_id=evaluator,
                candidate_digest=candidate.digest,
                quality=_quality(0.5),
                confidence=0.9,
                evidence_digest=f"{evaluator}-evidence-000000000000",
                method_id="sim",
            )
        )
    with pytest.raises(EvaluationError, match="quorum"):
        panel.decide(candidate.digest)


def test_panel_disagreement_forces_appeal() -> None:
    candidate = _candidate(Rival.A.value, "a", 0.5)
    panel = EvaluationPanel(
        ("j1", "j2", "j3"),
        max_axis_disagreement=0.2,
        minimum_method_diversity=2,
    )
    for evaluator, score, method in (
        ("j1", 0.2, "sim"),
        ("j2", 0.5, "sim"),
        ("j3", 0.9, "human"),
    ):
        panel.submit(
            JudgeVerdict.create(
                evaluator_id=evaluator,
                candidate_digest=candidate.digest,
                quality=_quality(score),
                confidence=0.9,
                evidence_digest=f"{evaluator}-evidence-000000000000",
                method_id=method,
            )
        )
    decision = panel.decide(candidate.digest)
    assert decision.eligible is False
    assert decision.requires_appeal is True
    assert set(decision.disagreement_axes) == set(QUALITY_AXES)


def test_blind_candidate_tokens_are_stable_but_salt_scoped() -> None:
    digest = "candidate-" + "a" * 64
    token = blind_candidate_token(digest, salt="salt-" + "b" * 64)
    assert token == blind_candidate_token(digest, salt="salt-" + "b" * 64)
    assert token != blind_candidate_token(digest, salt="salt-" + "c" * 64)


def test_resource_charge_is_atomic_on_limit_failure_and_has_no_time_budget() -> None:
    governor = _resources()
    governor.charge(ResourceDelta(tokens=100, tool_calls=2, active_branches=2))
    before = governor.snapshot
    with pytest.raises(ResourceLimitError, match="tokens"):
        governor.charge(ResourceDelta(tokens=2_000_000, tool_calls=999))
    after = governor.snapshot
    assert after == before
    assert not hasattr(governor.envelope, "max_seconds")
    assert governor.checkpoint_due(10)
    assert not governor.checkpoint_due(9)


def test_resource_checkpoint_is_tamper_evident() -> None:
    governor = _resources()
    governor.charge(ResourceDelta(tokens=1000, tool_calls=10, artifact_bytes=5000))
    checkpoint = governor.to_checkpoint()
    restored = ResourceGovernor.restore(checkpoint)
    assert restored.snapshot == governor.snapshot

    tampered = dict(checkpoint)
    usage = dict(tampered["usage"])
    usage["tokens"] = 2000
    tampered["usage"] = usage
    with pytest.raises(ResourceLimitError, match="digest mismatch"):
        ResourceGovernor.restore(tampered)


def test_quality_debt_is_non_compensable_and_ceiling_only_tightens() -> None:
    ledger = QualityDebtLedger(ceiling=12, protected_ceiling=0)
    ledger.add(
        DebtItem(
            debt_id="debt-1",
            axis="longform_consistency",
            severity=DebtSeverity.LOW,
            description="minor unresolved continuity contradiction",
            evidence_digest="debt-evidence-0000000000000000",
            opened_round=5,
            protected=True,
        )
    )
    assert not ledger.promotion_allowed()
    assert ledger.protected_score == 1
    ledger.resolve("debt-1", round_index=6)
    assert ledger.promotion_allowed()

    ledger.ratchet(ceiling=8)
    assert ledger.ceiling == 8
    with pytest.raises(QualityDebtError, match="only tighten"):
        ledger.ratchet(ceiling=12)


def test_control_plane_uses_panel_quality_not_candidate_self_score() -> None:
    incumbent = _candidate("seed", "s", 0.4)
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", 0.4)
    challenge = _challenge(Rival.B, built, "b", 0.4)
    panel, decision = _panel(challenge.improved_candidate, 0.3)
    control = ForgeControlPlane(
        forge=forge,
        evaluation_panel=panel,
        resource_governor=_resources(),
        quality_debt=QualityDebtLedger(),
    )
    control.submit_construct(built, resources=ResourceDelta(tokens=10))
    control.submit_attack(challenge, resources=ResourceDelta(tokens=10))
    receipt = control.reconcile(
        submitted=challenge.improved_candidate,
        panel_decision=decision,
        gate_results=_gates(),
        resources=ResourceDelta(tokens=10),
    )
    assert receipt.decision == "retain_incumbent"
    assert forge.champion.digest == incumbent.digest


def test_control_plane_promotes_only_with_quorum_and_zero_protected_debt() -> None:
    incumbent = _candidate("seed", "s", 0.4)
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", 0.5)
    challenge = _challenge(Rival.B, built, "b", 0.5)
    panel, decision = _panel(challenge.improved_candidate, 0.5)
    control = ForgeControlPlane(
        forge=forge,
        evaluation_panel=panel,
        resource_governor=_resources(),
        quality_debt=QualityDebtLedger(),
    )
    control.submit_construct(built, resources=ResourceDelta(tokens=10))
    control.submit_attack(challenge, resources=ResourceDelta(tokens=10))
    receipt = control.reconcile(
        submitted=challenge.improved_candidate,
        panel_decision=decision,
        gate_results=_gates(),
        resources=ResourceDelta(tokens=10),
    )
    assert decision.eligible
    assert receipt.decision == "promote"
    assert forge.champion.digest == challenge.improved_candidate.digest


def test_control_plane_quality_calibration_gate_blocks_inflated_self_score() -> None:
    incumbent = _candidate("seed", "s", 0.4)
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", 0.5)
    challenge = _challenge(Rival.B, built, "b", 0.9)
    panel, decision = _panel(challenge.improved_candidate, 0.5)
    control = ForgeControlPlane(
        forge=forge,
        evaluation_panel=panel,
        resource_governor=_resources(),
        quality_debt=QualityDebtLedger(),
    )
    control.submit_construct(built, resources=ResourceDelta(tokens=10))
    control.submit_attack(challenge, resources=ResourceDelta(tokens=10))
    receipt = control.reconcile(
        submitted=challenge.improved_candidate,
        panel_decision=decision,
        gate_results=_gates(),
        resources=ResourceDelta(tokens=10),
    )
    assert receipt.decision == "retain_incumbent"
    assert any(
        gate.gate_id == "quality_calibration" and not gate.passed
        for gate in receipt.gate_results
    )


def test_control_plane_checkpoint_bundle_is_content_addressed() -> None:
    control = ForgeControlPlane(
        forge=DualRivalForge(
            effort_mode=100,
            champion=_candidate("seed", "s", 0.4),
        ),
        evaluation_panel=EvaluationPanel(("j1", "j2", "j3")),
        resource_governor=_resources(),
        quality_debt=QualityDebtLedger(),
    )
    bundle = control.checkpoint_bundle()
    assert bundle["schema"] == "skeleton.ai_game_builder.control_plane.v1"
    assert isinstance(bundle["bundle_digest"], str)
    assert len(bundle["bundle_digest"]) == 64



def test_novelty_reservoir_rejects_repetitive_weaker_candidate() -> None:
    reservoir = NoveltyReservoir(capacity=4, minimum_distance=0.15)
    first = NoveltyRecord.create(
        candidate_digest="candidate-a-" + "a" * 32,
        quality_score=0.8,
        features={"mechanic": 0.5, "style": 0.5, "structure": 0.5},
    )
    repetitive = NoveltyRecord.create(
        candidate_digest="candidate-b-" + "b" * 32,
        quality_score=0.7,
        features={"mechanic": 0.51, "style": 0.49, "structure": 0.5},
    )
    assert reservoir.admit(first)
    assert not reservoir.admit(repetitive)
    assert [row.candidate_digest for row in reservoir.records] == [first.candidate_digest]


def test_dissent_resurfaces_when_dependency_changes() -> None:
    ledger = DissentLedger()
    objection = Objection(
        objection_id="OBJ-001",
        artifact_digest="artifact-" + "a" * 32,
        evidence_digest="evidence-" + "b" * 32,
        summary="late quest invalidates an early character promise",
        severity=8,
        dependency_ids=("quest.final", "character.arc"),
    )
    ledger.add(objection)
    blockers = ledger.blockers_for(
        artifact_digest="artifact-" + "z" * 32,
        changed_dependency_ids=("quest.final",),
    )
    assert blockers == (objection,)
    ledger.resolve("OBJ-001", resolution_digest="resolution-" + "c" * 32)
    assert ledger.blockers_for(
        artifact_digest=objection.artifact_digest,
        changed_dependency_ids=("quest.final",),
    ) == ()


def test_impact_graph_predicts_transitive_blast_radius() -> None:
    graph = ImpactGraph()
    graph.add_node("project.dna")
    graph.add_node("combat.rules", depends_on=("project.dna",))
    graph.add_node("boss.scene", depends_on=("combat.rules",))
    graph.add_node("ending", depends_on=("boss.scene",))
    assert graph.blast_radius(("combat.rules",)) == (
        "boss.scene",
        "combat.rules",
        "ending",
    )
    assert graph.calibration(
        ("combat.rules", "boss.scene", "ending"),
        ("combat.rules", "ending"),
    ) == {"precision": 2 / 3, "recall": 1.0}


def test_impact_graph_rejects_unknown_dependency() -> None:
    graph = ImpactGraph()
    graph.add_node("root")
    with pytest.raises(ResilienceError, match="unknown impact dependencies"):
        graph.add_node("child", depends_on=("missing",))


def test_invariant_registry_rejects_ambiguous_cross_pillar_duplicate() -> None:
    registry = InvariantRegistry()
    registry.add(
        Invariant(
            invariant_id="INV-001",
            scope="combat",
            expression="player_damage >= 0",
            source_pillar="fairness",
            severity=8,
            inherited_by=("boss.scene",),
        )
    )
    assert registry.applicable("boss.scene")[0].invariant_id == "INV-001"
    with pytest.raises(ResilienceError, match="ambiguous duplicate invariant"):
        registry.add(
            Invariant(
                invariant_id="INV-002",
                scope="combat",
                expression="player_damage >= 0",
                source_pillar="realism",
                severity=4,
            )
        )


def _gold_bundle(*, failed_family: str | None = None) -> GoldMasterBundle:
    families = [
        FamilyQualification(
            family_id=f"GB{i:02d}",
            passed=f"GB{i:02d}" != failed_family,
            evidence_digest=f"family-{i:02d}-" + "e" * 24,
        )
        for i in range(1, 51)
    ]
    return GoldMasterBundle.create(
        artifact_digest="artifact-" + "a" * 32,
        build_digest="build-" + "b" * 32,
        canon_digest="canon-" + "c" * 32,
        provenance_digest="provenance-" + "d" * 32,
        replay_digest="replay-" + "e" * 32,
        rollback_target_digest="rollback-" + "f" * 32,
        red_team_digest="redteam-" + "1" * 32,
        family_qualifications=families,
        critical_gate_results={
            "rights": (True, "rights-" + "2" * 32),
            "security": (True, "security-" + "3" * 32),
            "reproducibility": (True, "repro-" + "4" * 32),
        },
    )


def test_gold_master_rejects_truthy_non_boolean_family_state() -> None:
    with pytest.raises(TypeError, match="family qualification passed state must be boolean"):
        FamilyQualification(
            family_id="GB01",
            passed="false",
            evidence_digest="family-01-" + "e" * 24,
        )


def test_gold_master_rejects_truthy_non_boolean_critical_gate_state() -> None:
    from skeleton.ai.game_builder.release import CriticalGateQualification

    with pytest.raises(TypeError, match="critical gate passed state must be boolean"):
        CriticalGateQualification(
            gate_id="rights",
            passed="false",
            evidence_digest="rights-" + "2" * 32,
        )


def test_gold_master_rejects_truthy_non_boolean_tribunal_vote() -> None:
    bundle = _gold_bundle()
    with pytest.raises(TypeError, match="tribunal vote accept state must be boolean"):
        TribunalVote(
            authority_id="gm-1",
            bundle_digest=bundle.digest,
            accept="false",
            evidence_digest="gm-1-evidence-" + "a" * 24,
            rationale_digest="gm-1-rationale-" + "b" * 24,
        )


def test_gold_master_requires_all_fifty_families() -> None:
    tribunal = GoldMasterTribunal(("gm-1", "gm-2", "gm-3"))
    with pytest.raises(ReleaseArbitrationError, match="failed family or critical-gate qualification"):
        tribunal.decide(_gold_bundle(failed_family="GB47"))


def test_gold_master_requires_unanimous_independent_quorum() -> None:
    bundle = _gold_bundle()
    tribunal = GoldMasterTribunal(("gm-1", "gm-2", "gm-3"))
    for authority, accept in (("gm-1", True), ("gm-2", True), ("gm-3", False)):
        tribunal.vote(
            TribunalVote(
                authority_id=authority,
                bundle_digest=bundle.digest,
                accept=accept,
                evidence_digest=f"{authority}-evidence-" + "a" * 24,
                rationale_digest=f"{authority}-rationale-" + "b" * 24,
            )
        )
    verdict = tribunal.decide(bundle)
    assert verdict.accepted is False
    assert len(verdict.authority_ids) == 3
    assert len(verdict.vote_digests) == 3



def test_gold_master_failed_critical_gate_blocks_release() -> None:
    families = [
        FamilyQualification(
            family_id=f"GB{i:02d}",
            passed=True,
            evidence_digest=f"family-{i:02d}-" + "e" * 24,
        )
        for i in range(1, 51)
    ]
    bundle = GoldMasterBundle.create(
        artifact_digest="artifact-" + "a" * 32,
        build_digest="build-" + "b" * 32,
        canon_digest="canon-" + "c" * 32,
        provenance_digest="provenance-" + "d" * 32,
        replay_digest="replay-" + "e" * 32,
        rollback_target_digest="rollback-" + "f" * 32,
        red_team_digest="redteam-" + "1" * 32,
        family_qualifications=families,
        critical_gate_results={
            "rights": (False, "rights-" + "2" * 32),
            "security": (True, "security-" + "3" * 32),
        },
    )
    tribunal = GoldMasterTribunal(("gm-1", "gm-2", "gm-3"))
    with pytest.raises(
        ReleaseArbitrationError,
        match="failed family or critical-gate qualification",
    ):
        tribunal.decide(bundle)


def test_gold_master_excludes_routine_evaluators() -> None:
    with pytest.raises(ValueError, match="forbidden authority"):
        GoldMasterTribunal(
            ("gm-1", "judge-1", "gm-3"),
            routine_evaluator_ids=("judge-1", "judge-2"),
        )
