from __future__ import annotations

import json

import pytest

from skeleton.ai.runtime.inference.developmental_eval import (
    DevelopmentalEvalCase,
    DevelopmentalEvalSuite,
    DevelopmentalEvaluationError,
    evaluate_local_candidate_developmentally,
    evaluate_training_receipt_developmentally,
)
from skeleton.ai.runtime.inference.artifact import load_local_model_artifact
from skeleton.ai.runtime.inference.local import ReferenceNGramModel
from skeleton.ai.runtime.inference.training_allocation import (
    TrainingAllocationPolicy,
    allocate_training_methods,
)
from skeleton.ai.runtime.inference.training_methods import (
    TrainingExample,
    TrainingMethod,
    compile_training_plan,
)


def _write_reference_artifact(tmp_path, name: str, corpus: tuple[str, ...]):
    model = ReferenceNGramModel.train(
        corpus,
        order=1,
        model_id=name,
    )
    path = tmp_path / f"{name}.json"
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
    return path, model


def test_developmental_eval_measures_real_candidate_gain_and_feeds_allocator(
    tmp_path,
) -> None:
    baseline_path, baseline = _write_reference_artifact(
        tmp_path,
        "baseline-blue",
        ("color blue",),
    )
    candidate_path, candidate = _write_reference_artifact(
        tmp_path,
        "candidate-red",
        ("color red",),
    )
    suite = DevelopmentalEvalSuite(
        suite_id="color-development",
        cases=(
            DevelopmentalEvalCase(
                case_id="color-answer",
                prompt="color",
                required_terms=("red",),
                forbidden_terms=("blue",),
                max_output_tokens=4,
                seed=0,
            ),
        ),
    )
    plan_digest = "a" * 64

    plan = compile_training_plan(
        (
            TrainingExample(
                example_id="development-attribution",
                prompt="color",
                response="red",
            ),
        ),
        methods=(TrainingMethod.SUPERVISED_INSTRUCTION,),
    )
    loaded_candidate = load_local_model_artifact(candidate_path)
    candidate_receipt = {
        "output_path": str(candidate_path),
        "model_digest": loaded_candidate.receipt.model_digest,
        "artifact_sha256": loaded_candidate.receipt.artifact_sha256,
        "training_plan": plan.as_dict(),
    }

    report = evaluate_training_receipt_developmentally(
        baseline_path=baseline_path,
        candidate_receipt=candidate_receipt,
        suite=suite,
        method=TrainingMethod.SUPERVISED_INSTRUCTION,
    )

    assert report.baseline_model_digest == baseline.model_digest
    assert report.candidate_model_digest == candidate.model_digest
    assert report.baseline_score == 0.0
    assert report.candidate_score == 1.0
    assert report.validation_gain == 1.0
    assert report.production_authority is False
    assert len(report.digest) == 64

    observation = report.allocation_observation()
    assert observation.evaluation_class == "development"
    assert observation.validation_gain == 1.0
    assert observation.evaluation_digest == report.digest
    assert observation.plan_digest == plan.plan_digest
    assert report.attribution_verified is True

    allocation = allocate_training_methods(
        (observation,),
        available_methods=(TrainingMethod.SUPERVISED_INSTRUCTION,),
        policy=TrainingAllocationPolicy(
            max_repeat_per_method=4,
            max_total_repeats=4,
            mandatory_methods=(TrainingMethod.SUPERVISED_INSTRUCTION,),
        ),
    )
    assert allocation.method_weights[0].method is TrainingMethod.SUPERVISED_INSTRUCTION
    assert allocation.method_weights[0].repeat == 4


def test_developmental_eval_rejects_same_model_as_baseline_and_candidate(
    tmp_path,
) -> None:
    path, _model = _write_reference_artifact(
        tmp_path,
        "same-model",
        ("color red",),
    )
    suite = DevelopmentalEvalSuite(
        suite_id="same-model-check",
        cases=(
            DevelopmentalEvalCase(
                case_id="case-1",
                prompt="color",
                required_terms=("red",),
            ),
        ),
    )

    with pytest.raises(
        DevelopmentalEvaluationError,
        match="must be distinct",
    ):
        evaluate_local_candidate_developmentally(
            baseline_path=path,
            candidate_path=path,
            suite=suite,
            training_plan_digest="b" * 64,
            method=TrainingMethod.SUPERVISED_INSTRUCTION,
        )


def test_developmental_suite_rejects_ambiguous_required_forbidden_term() -> None:
    with pytest.raises(
        DevelopmentalEvaluationError,
        match="must be disjoint",
    ):
        DevelopmentalEvalCase(
            case_id="ambiguous",
            prompt="answer",
            required_terms=("safe",),
            forbidden_terms=("SAFE",),
        )


def test_generic_developmental_comparison_cannot_feed_allocator(
    tmp_path,
) -> None:
    baseline_path, _baseline = _write_reference_artifact(
        tmp_path,
        "diagnostic-baseline",
        ("color blue",),
    )
    candidate_path, _candidate = _write_reference_artifact(
        tmp_path,
        "diagnostic-candidate",
        ("color red",),
    )
    suite = DevelopmentalEvalSuite(
        suite_id="diagnostic-only",
        cases=(
            DevelopmentalEvalCase(
                case_id="diagnostic-case",
                prompt="color",
                required_terms=("red",),
            ),
        ),
    )
    report = evaluate_local_candidate_developmentally(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
        suite=suite,
        training_plan_digest="c" * 64,
        method=TrainingMethod.SUPERVISED_INSTRUCTION,
    )
    assert report.attribution_verified is False
    with pytest.raises(
        DevelopmentalEvaluationError,
        match="requires verified training-method attribution",
    ):
        report.allocation_observation()
