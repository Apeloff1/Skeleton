from __future__ import annotations

import json
from dataclasses import replace

import pytest

from skeleton.ai.runtime.inference.continual_learning import (
    ContinualLearningError,
    ContinualLearningPolicy,
    ContinualLearningRound,
    ContinualLearningState,
    DevelopmentalChampion,
    initialize_continual_learning_state,
    load_continual_learning_state,
    rollback_developmental_champion,
    run_continual_learning_round,
    save_continual_learning_state,
)
from skeleton.ai.runtime.inference.developmental_eval import (
    DevelopmentalEvalCase,
    DevelopmentalEvalSuite,
)
from skeleton.ai.runtime.inference.local import ReferenceNGramModel
from skeleton.ai.runtime.inference.training_allocation import (
    TrainingAllocationPolicy,
)
from skeleton.ai.runtime.inference.training_methods import (
    TrainingExample,
    TrainingMethod,
)
from skeleton.ai.runtime.inference.training_optimizer import (
    TrainingOptimizationPolicy,
)


MANDATORY = (
    TrainingMethod.SUPERVISED_INSTRUCTION,
    TrainingMethod.CAUSAL_LANGUAGE_MODELING,
    TrainingMethod.SELF_SUPERVISED_SPAN,
)


def _baseline(tmp_path):
    model = ReferenceNGramModel.train(
        ("answer baseline",),
        order=1,
        model_id="continual-baseline",
    )
    path = tmp_path / "continual-baseline.json"
    path.write_text(
        json.dumps(
            model.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    return path


def _suite(suite_id: str, term: str) -> DevelopmentalEvalSuite:
    return DevelopmentalEvalSuite(
        suite_id=suite_id,
        cases=(
            DevelopmentalEvalCase(
                case_id=suite_id + "-case",
                prompt="answer",
                required_terms=(term,),
                max_output_tokens=6,
                seed=0,
            ),
        ),
    )


def _round_kwargs(tmp_path):
    return {
        "work_dir": tmp_path,
        "requested_methods": MANDATORY,
        "allocation_policy": TrainingAllocationPolicy(
            max_repeat_per_method=2,
            max_total_repeats=6,
            mandatory_methods=MANDATORY,
        ),
        "optimization_policy": TrainingOptimizationPolicy(
            max_probes=3,
            probe_epochs=1,
            probe_gradient_accumulation_steps=1,
            final_gradient_accumulation_steps=2,
            cleanup_probe_artifacts=True,
        ),
        "hidden_size": 8,
        "final_epochs": 1,
        "learning_rate": 0.03,
        "max_vocab": 64,
        "max_document_tokens": 64,
        "seed": 53,
        "temperature": 0.7,
    }


def test_continual_round_accepts_persists_replays_and_rolls_back(
    tmp_path,
) -> None:
    pytest.importorskip("numpy")
    baseline = _baseline(tmp_path)
    initial = initialize_continual_learning_state(
        lineage_id="continual-fixture",
        baseline_path=baseline,
    )
    generation_zero = initial.active_champion

    first, first_round = run_continual_learning_round(
        state=initial,
        new_examples=(
            TrainingExample(
                example_id="generation-one",
                prompt="answer",
                response="target",
                source_ref="continual:test:g1",
            ),
        ),
        acquisition_suite=_suite("acquisition-one", "target"),
        retention_suite=_suite("retention-one", "baseline"),
        challenger_output_path=tmp_path / "generation-one.json",
        model_id="continual-generation-one",
        policy=ContinualLearningPolicy(
            max_replay_items=8,
            replay_examples_per_round=4,
            minimum_acquisition_gain=-1.0,
            maximum_retention_drop=1.0,
        ),
        **_round_kwargs(tmp_path),
    )

    assert first_round.accepted is True
    assert first.active_champion.generation == 1
    assert first.active_champion.model_digest != generation_zero.model_digest
    assert len(first.champions) == 2
    assert len(first.replay_memory) == 1
    assert first.replay_memory[0].example.replay is True
    assert first_round.replay_example_digests == ()

    state_path = tmp_path / "continual-state.json"
    digest = save_continual_learning_state(first, state_path)
    loaded = load_continual_learning_state(state_path)
    assert loaded.digest == digest
    assert loaded.as_dict() == first.as_dict()

    second, second_round = run_continual_learning_round(
        state=loaded,
        new_examples=(
            TrainingExample(
                example_id="generation-two-rejected",
                prompt="answer",
                response="second-target",
                source_ref="continual:test:g2",
            ),
        ),
        acquisition_suite=_suite(
            "acquisition-impossible",
            "never-present-token-xyz",
        ),
        retention_suite=_suite("retention-two", "target"),
        challenger_output_path=tmp_path / "generation-two-rejected.json",
        model_id="continual-generation-two",
        policy=ContinualLearningPolicy(
            max_replay_items=8,
            replay_examples_per_round=4,
            minimum_acquisition_gain=1.0,
            maximum_retention_drop=1.0,
            cleanup_rejected_candidates=True,
        ),
        **_round_kwargs(tmp_path),
    )

    assert second_round.accepted is False
    assert "insufficient-acquisition-gain" in second_round.reason
    assert second.active_champion.model_digest == first.active_champion.model_digest
    assert len(second.champions) == 2
    assert len(second.rounds) == 2
    assert second_round.replay_example_digests
    assert not (tmp_path / "generation-two-rejected.json").exists()

    rolled_back = rollback_developmental_champion(
        second,
        champion_model_digest=generation_zero.model_digest,
    )
    assert rolled_back.active_champion.generation == 0
    assert rolled_back.active_champion.model_digest == generation_zero.model_digest
    assert len(rolled_back.rounds) == 2
    assert len(rolled_back.replay_memory) == 1


def test_continual_state_rejects_digest_tampering(tmp_path) -> None:
    baseline = _baseline(tmp_path)
    state = initialize_continual_learning_state(
        lineage_id="tamper-fixture",
        baseline_path=baseline,
    )
    path = tmp_path / "tampered-state.json"
    save_continual_learning_state(state, path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["lineage_id"] = "tampered-lineage"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        ContinualLearningError,
        match="state digest mismatch",
    ):
        load_continual_learning_state(path)


def test_continual_state_detects_champion_artifact_drift(tmp_path) -> None:
    baseline = _baseline(tmp_path)
    state = initialize_continual_learning_state(
        lineage_id="artifact-drift",
        baseline_path=baseline,
    )
    path = tmp_path / "artifact-state.json"
    save_continual_learning_state(state, path)

    baseline.write_text("{}", encoding="utf-8")

    with pytest.raises(
        ContinualLearningError,
        match="champion artifact",
    ):
        load_continual_learning_state(path)



def test_continual_state_binds_accepted_round_to_exact_champion(
    tmp_path,
) -> None:
    baseline = _baseline(tmp_path)
    initial = initialize_continual_learning_state(
        lineage_id="lineage-graph",
        baseline_path=baseline,
    )
    parent = initial.active_champion
    round_record = ContinualLearningRound(
        round_index=1,
        baseline_champion_digest=parent.digest,
        challenger_model_digest="a" * 64,
        challenger_artifact_sha256="b" * 64,
        challenger_artifact_path=str(tmp_path / "candidate.json"),
        optimization_digest="c" * 64,
        acquisition_report_digest="d" * 64,
        retention_report_digest="e" * 64,
        replay_example_digests=(),
        new_example_digests=("f" * 64,),
        acquisition_gain=0.1,
        retention_gain=0.0,
        accepted=True,
        reason="accepted-developmental-challenger",
        policy_digest="1" * 64,
    )
    child = DevelopmentalChampion(
        generation=1,
        artifact_path=round_record.challenger_artifact_path,
        model_id="candidate",
        model_digest=round_record.challenger_model_digest,
        artifact_sha256=round_record.challenger_artifact_sha256,
        source_round_digest=round_record.digest,
        training_plan_digest="2" * 64,
    )

    valid = ContinualLearningState(
        lineage_id=initial.lineage_id,
        champions=(parent, child),
        active_champion_index=1,
        rounds=(round_record,),
    )
    assert valid.active_champion.digest == child.digest

    with pytest.raises(
        ContinualLearningError,
        match="accepted round must identify exactly one champion",
    ):
        ContinualLearningState(
            lineage_id=initial.lineage_id,
            champions=(
                parent,
                replace(child, source_round_digest="3" * 64),
            ),
            active_champion_index=1,
            rounds=(round_record,),
        )

    with pytest.raises(
        ContinualLearningError,
        match="accepted round and champion identity drift",
    ):
        ContinualLearningState(
            lineage_id=initial.lineage_id,
            champions=(
                parent,
                replace(child, artifact_sha256="4" * 64),
            ),
            active_champion_index=1,
            rounds=(round_record,),
        )
