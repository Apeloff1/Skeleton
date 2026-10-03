from __future__ import annotations

import json

import pytest

from skeleton.ai.runtime.inference.continual_learning import (
    ContinualLearningPolicy,
    initialize_continual_learning_state,
)
from skeleton.ai.runtime.inference.curriculum import (
    CapabilityObjective,
    CurriculumPolicy,
    plan_capability_curriculum,
    run_curriculum_learning_round,
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
        ("answer alpha",),
        order=1,
        model_id="curriculum-baseline",
    )
    path = tmp_path / "curriculum-baseline.json"
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


def _suite(name: str, required: str) -> DevelopmentalEvalSuite:
    return DevelopmentalEvalSuite(
        suite_id=name,
        cases=(
            DevelopmentalEvalCase(
                case_id=name + "-case",
                prompt="answer",
                required_terms=(required,),
                max_output_tokens=4,
                seed=0,
            ),
        ),
    )


def _objectives() -> tuple[CapabilityObjective, ...]:
    return (
        CapabilityObjective(
            capability_id="foundation-alpha",
            suite=_suite("alpha-suite", "alpha"),
            minimum_score=1.0,
            priority=10.0,
            method_hints=MANDATORY,
        ),
        CapabilityObjective(
            capability_id="skill-beta",
            suite=_suite("beta-suite", "beta"),
            minimum_score=1.0,
            priority=5.0,
            dependencies=("foundation-alpha",),
            method_hints=MANDATORY,
        ),
        CapabilityObjective(
            capability_id="skill-gamma",
            suite=_suite("gamma-suite", "gamma"),
            minimum_score=1.0,
            priority=100.0,
            dependencies=("skill-beta",),
            method_hints=MANDATORY,
        ),
    )


def test_curriculum_respects_dependencies_before_priority(tmp_path) -> None:
    baseline = _baseline(tmp_path)
    plan = plan_capability_curriculum(
        model_path=baseline,
        objectives=_objectives(),
        policy=CurriculumPolicy(max_targets_per_round=2),
    )

    by_id = {
        item.capability_id: item for item in plan.assessments
    }
    assert by_id["foundation-alpha"].mastered is True
    assert by_id["skill-beta"].eligible is True
    assert by_id["skill-gamma"].eligible is False
    assert plan.target_capability_ids == ("skill-beta",)
    assert set(plan.selected_methods) == set(MANDATORY)
    assert plan.acquisition_suite is not None
    assert plan.retention_suite is not None
    assert plan.complete is False


def test_curriculum_round_selects_target_and_runs_continual_learning(
    tmp_path,
) -> None:
    pytest.importorskip("numpy")
    baseline = _baseline(tmp_path)
    state = initialize_continual_learning_state(
        lineage_id="curriculum-lineage",
        baseline_path=baseline,
    )

    result = run_curriculum_learning_round(
        state=state,
        objectives=_objectives(),
        examples_by_capability={
            "skill-beta": (
                TrainingExample(
                    example_id="learn-beta",
                    prompt="answer",
                    response="beta",
                    source_ref="curriculum:test:beta",
                ),
            ),
            "skill-gamma": (
                TrainingExample(
                    example_id="learn-gamma",
                    prompt="answer",
                    response="gamma",
                    source_ref="curriculum:test:gamma",
                ),
            ),
        },
        work_dir=tmp_path,
        challenger_output_path=tmp_path / "curriculum-challenger.json",
        model_id="curriculum-challenger",
        curriculum_policy=CurriculumPolicy(
            max_targets_per_round=1,
        ),
        continual_policy=ContinualLearningPolicy(
            max_replay_items=8,
            replay_examples_per_round=4,
            minimum_acquisition_gain=-1.0,
            maximum_retention_drop=1.0,
        ),
        allocation_policy=TrainingAllocationPolicy(
            max_repeat_per_method=2,
            max_total_repeats=6,
            mandatory_methods=MANDATORY,
        ),
        optimization_policy=TrainingOptimizationPolicy(
            max_probes=3,
            probe_epochs=1,
            probe_gradient_accumulation_steps=1,
            final_gradient_accumulation_steps=2,
        ),
        hidden_size=8,
        final_epochs=1,
        learning_rate=0.03,
        max_vocab=64,
        max_document_tokens=64,
        seed=61,
        temperature=0.7,
    )

    assert result.before.target_capability_ids == ("skill-beta",)
    assert result.continual_round is not None
    assert result.continual_round.accepted is True
    assert result.state.active_champion.generation == 1
    assert len(result.state.replay_memory) == 1
    assert result.after.model_digest == result.state.active_champion.model_digest
    assert result.digest


def test_mastered_curriculum_is_noop(tmp_path) -> None:
    baseline = _baseline(tmp_path)
    state = initialize_continual_learning_state(
        lineage_id="complete-curriculum",
        baseline_path=baseline,
    )
    objectives = (
        CapabilityObjective(
            capability_id="only-alpha",
            suite=_suite("only-alpha-suite", "alpha"),
            minimum_score=1.0,
            method_hints=MANDATORY,
        ),
    )

    result = run_curriculum_learning_round(
        state=state,
        objectives=objectives,
        examples_by_capability={},
        work_dir=tmp_path,
        challenger_output_path=tmp_path / "should-not-exist.json",
        model_id="unused",
    )

    assert result.before.complete is True
    assert result.continual_round is None
    assert result.state.digest == state.digest
    assert result.after.plan_digest == result.before.plan_digest
    assert not (tmp_path / "should-not-exist.json").exists()
