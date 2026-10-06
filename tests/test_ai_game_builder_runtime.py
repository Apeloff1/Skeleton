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

from skeleton.ai.game_builder.contracts import (  # noqa: E402
    ArtifactIdentity,
    Candidate,
    Challenge,
    EffortMode,
    GateResult,
    PromotionReceipt,
    QUALITY_AXES,
    Rival,
    Stage,
    canonical_digest,
)
from skeleton.ai.game_builder.dual_rival_forge import DualRivalForge, ForgeStateError  # noqa: E402


def _quality(value: float = 0.5, **updates: float) -> dict[str, float]:
    result = {axis: value for axis in QUALITY_AXES}
    result.update(updates)
    return result


def _candidate(
    producer: str,
    token: str,
    *,
    quality: dict[str, float] | None = None,
    parents: tuple[str, ...] = (),
) -> Candidate:
    suffix = (token * 32)[:32]
    return Candidate.create(
        producer_id=producer,
        artifact=ArtifactIdentity(
            artifact_digest=f"artifact-{suffix}",
            canon_digest=f"canon-{suffix}",
            provenance_digest=f"provenance-{suffix}",
            family_id="GB03",
            level_id="GBL-021",
        ),
        quality=quality or _quality(),
        evidence_digests=(f"evidence-{suffix}",),
        assumption_digest=f"assumption-{suffix}",
        parent_candidate_digests=parents,
    )


def _challenge(challenger: Rival, target: Candidate, token: str) -> Challenge:
    improved = _candidate(challenger.value, token)
    return Challenge(
        challenger_id=challenger.value,
        target_candidate_digest=target.digest,
        attack_digest=f"attack-{(token * 32)[:32]}",
        improved_candidate=improved,
        counterexample_digests=(f"counterexample-{(token * 32)[:32]}",),
    )


def _gates(*, passed: bool = True) -> tuple[GateResult, ...]:
    return (
        GateResult("rights", passed, "evidence-rights-0000000000000000"),
        GateResult("continuity", passed, "evidence-canon-00000000000000000"),
        GateResult("state", passed, "evidence-state-000000000000000000"),
    )


def test_effort_modes_are_exact_and_have_three_stage_executions() -> None:
    assert EffortMode.FORGE_100.rounds == 100
    assert EffortMode.FORGE_1000.rounds == 1000
    assert EffortMode.FORGE_10000.rounds == 10000
    assert EffortMode.FORGE_100.stage_executions == 300
    assert EffortMode.FORGE_1000.stage_executions == 3000
    assert EffortMode.FORGE_10000.stage_executions == 30000


def test_stage_order_and_role_rotation_are_fail_closed() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "s"))
    with pytest.raises(ForgeStateError, match="attack submission is out of stage order"):
        forge.submit_attack(_challenge(Rival.B, _candidate(Rival.A.value, "a"), "b"))

    built = _candidate(Rival.A.value, "a")
    assert forge.submit_construct(built).stage is Stage.ATTACK_AND_IMPROVE
    with pytest.raises(ForgeStateError, match="construct submission is out of stage order"):
        forge.submit_construct(built)

    attack = _challenge(Rival.B, built, "b")
    assert forge.submit_attack(attack).stage is Stage.RECONCILE_AND_PROMOTE
    forge.reconcile(submitted=None, evaluator_id="independent-judge", gate_results=_gates())

    assert forge.completed_rounds == 1
    assert forge.builder is Rival.B
    assert forge.challenger is Rival.A
    assert forge.stage is Stage.CONSTRUCT


def test_compensable_only_gate_set_cannot_promote() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    receipt = forge.reconcile(
        submitted=challenge.improved_candidate,
        evaluator_id="independent-judge",
        gate_results=(
            GateResult(
                "advisory",
                True,
                "evidence-advisory-0000000000000000",
                non_compensable=False,
            ),
        ),
    )

    assert receipt.decision == "retain_incumbent"
    assert forge.champion.digest == incumbent.digest


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("passed", 1, "passed state must be boolean"),
        ("passed", "false", "passed state must be boolean"),
        ("non_compensable", 1, "non_compensable state must be boolean"),
        ("non_compensable", "false", "non_compensable state must be boolean"),
    ],
)
def test_gate_result_rejects_non_boolean_authority_states(
    field: str,
    value: object,
    message: str,
) -> None:
    kwargs = {
        "gate_id": "rights",
        "passed": True,
        "evidence_digest": "evidence-rights-0000000000000000",
        "non_compensable": True,
    }
    kwargs[field] = value
    with pytest.raises(TypeError, match=message):
        GateResult(**kwargs)


def test_duplicate_gate_ids_are_rejected_before_promotion() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    duplicate = GateResult(
        "rights",
        True,
        "evidence-rights-1111111111111111",
    )
    with pytest.raises(ValueError, match="unique gate ids"):
        forge.reconcile(
            submitted=challenge.improved_candidate,
            evaluator_id="independent-judge",
            gate_results=(_gates()[0], duplicate),
        )


def test_malformed_gate_object_is_rejected_before_promotion() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    with pytest.raises(TypeError, match="GateResult"):
        forge.reconcile(
            submitted=challenge.improved_candidate,
            evaluator_id="independent-judge",
            gate_results=(object(),),
        )


def test_non_compensable_gate_failure_retains_incumbent() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.7))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    receipt = forge.reconcile(
        submitted=challenge.improved_candidate,
        evaluator_id="independent-judge",
        gate_results=_gates(passed=False),
    )
    assert receipt.decision == "retain_incumbent"
    assert forge.champion.digest == incumbent.digest


def test_pareto_safe_candidate_promotes_with_independent_judge() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    improved = _candidate(
        Rival.B.value,
        "b",
        quality=_quality(
            0.5,
            longform_consistency=0.6,
            rights_provenance_safety=0.7,
        ),
    )
    forge.submit_attack(
        Challenge(
            challenger_id=Rival.B.value,
            target_candidate_digest=built.digest,
            attack_digest="attack-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            improved_candidate=improved,
            counterexample_digests=("counter-bbbbbbbbbbbbbbbbbbbbbbbbbbbbb",),
        )
    )
    receipt = forge.reconcile(
        submitted=improved,
        evaluator_id="independent-judge",
        gate_results=_gates(),
    )
    assert receipt.decision == "promote"
    assert forge.champion.digest == improved.digest


@pytest.mark.parametrize("evaluator", [Rival.A.value, Rival.B.value])
def test_rivals_cannot_be_final_promotion_judge(evaluator: str) -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "s"))
    built = _candidate(Rival.A.value, "a")
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)
    with pytest.raises(ValueError, match="independent"):
        forge.reconcile(
            submitted=challenge.improved_candidate,
            evaluator_id=evaluator,
            gate_results=_gates(),
        )


def test_synthesis_requires_both_parent_candidates_and_non_rival_identity() -> None:
    forge = DualRivalForge(
        effort_mode=100,
        champion=_candidate("seed", "s", quality=_quality(0.3)),
    )
    built = _candidate(Rival.A.value, "a", quality=_quality(0.4))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    bad = _candidate("synthesis", "x", quality=_quality(0.6), parents=(built.digest,))
    with pytest.raises(ForgeStateError, match="must name both"):
        forge.reconcile(
            submitted=bad,
            evaluator_id="independent-judge",
            gate_results=_gates(),
        )

    synthesis = _candidate(
        "synthesis:rival_a+rival_b",
        "y",
        quality=_quality(0.6),
        parents=(built.digest, challenge.improved_candidate.digest),
    )
    receipt = forge.reconcile(
        submitted=synthesis,
        evaluator_id="independent-judge",
        gate_results=_gates(),
    )
    assert receipt.decision == "promote"
    assert forge.champion.digest == synthesis.digest


def test_checkpoint_round_trip_preserves_pending_attack_state() -> None:
    forge = DualRivalForge(effort_mode="forge_1000", champion=_candidate("seed", "s"))
    built = _candidate(Rival.A.value, "a")
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)

    checkpoint = forge.checkpoint()
    restored = DualRivalForge.restore(checkpoint)

    assert restored.status.to_payload() == forge.status.to_payload()
    assert restored.pending_construct is not None
    assert restored.pending_construct.digest == built.digest
    assert restored.pending_challenge is not None
    assert restored.pending_challenge.digest == challenge.digest

    tampered = dict(checkpoint)
    tampered["round_index"] = 999
    with pytest.raises(ForgeStateError, match="checkpoint digest mismatch"):
        DualRivalForge.restore(tampered)


def test_promotion_receipt_rehashes_public_decision_evidence() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)
    receipt = forge.reconcile(
        submitted=challenge.improved_candidate,
        evaluator_id="independent-judge",
        gate_results=_gates(),
    )

    assert canonical_digest(receipt.decision_payload()) == receipt.decision_digest
    with pytest.raises(ValueError, match="decision digest mismatch"):
        PromotionReceipt(
            round_index=receipt.round_index,
            effort_mode=receipt.effort_mode,
            incumbent_digest=receipt.incumbent_digest,
            submitted_digest=receipt.submitted_digest,
            promoted_digest=receipt.promoted_digest,
            evaluator_id=receipt.evaluator_id,
            gate_results=receipt.gate_results,
            evaluated_submitted_quality=receipt.evaluated_submitted_quality,
            decision=receipt.decision,
            decision_digest="tampered-" + "0" * 64,
        )


def test_forge_rejects_completed_round_count_without_receipt_history() -> None:
    with pytest.raises(
        ForgeStateError,
        match="completed_rounds must equal promotion receipt count",
    ):
        DualRivalForge(
            effort_mode=100,
            champion=_candidate("seed", "s"),
            completed_rounds=1,
            round_index=2,
        )


def test_forge_rejects_terminal_champion_not_bound_to_receipt_chain() -> None:
    incumbent = _candidate("seed", "s", quality=_quality(0.4))
    forge = DualRivalForge(effort_mode=100, champion=incumbent)
    built = _candidate(Rival.A.value, "a", quality=_quality(0.5))
    forge.submit_construct(built)
    challenge = _challenge(Rival.B, built, "b")
    forge.submit_attack(challenge)
    receipt = forge.reconcile(
        submitted=None,
        evaluator_id="independent-judge",
        gate_results=_gates(),
    )

    with pytest.raises(
        ForgeStateError,
        match="forge champion must match terminal promotion receipt",
    ):
        DualRivalForge(
            effort_mode=100,
            champion=_candidate("seed", "different"),
            builder=Rival.B,
            completed_rounds=1,
            round_index=2,
            receipts=(receipt,),
        )


def test_self_consistent_forged_checkpoint_cannot_invent_completed_rounds() -> None:
    forge = DualRivalForge(effort_mode=100, champion=_candidate("seed", "s"))
    checkpoint = forge.checkpoint()
    forged = {
        key: value
        for key, value in checkpoint.items()
        if key != "checkpoint_digest"
    }
    forged["completed_rounds"] = 1
    forged["round_index"] = 2
    forged["receipt_digests"] = []
    forged["checkpoint_digest"] = canonical_digest(
        {key: value for key, value in forged.items() if key != "checkpoint_digest"}
    )

    with pytest.raises(
        ForgeStateError,
        match="completed_rounds must equal promotion receipt count",
    ):
        DualRivalForge.restore(forged)


def test_forge_100_completes_only_after_exactly_100_three_stage_rounds() -> None:
    forge = DualRivalForge(
        effort_mode=EffortMode.FORGE_100,
        champion=_candidate("seed", "s"),
    )
    for round_number in range(1, 101):
        builder = forge.builder
        challenger = forge.challenger
        built = _candidate(builder.value, f"a{round_number}")
        forge.submit_construct(built)
        forge.submit_attack(_challenge(challenger, built, f"b{round_number}"))
        forge.reconcile(
            submitted=None,
            evaluator_id="independent-judge",
            gate_results=_gates(),
        )
        assert forge.completed_rounds == round_number

    assert forge.completed is True
    assert forge.completed_rounds == 100
    assert forge.status.remaining_rounds == 0
    with pytest.raises(ForgeStateError, match="round budget is complete"):
        forge.submit_construct(_candidate(forge.builder.value, "final"))
