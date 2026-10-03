from __future__ import annotations

import json

import pytest

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
    optimize_training_mix,
)


def _baseline(tmp_path):
    model = ReferenceNGramModel.train(
        ("answer baseline",),
        order=1,
        model_id="optimizer-baseline",
    )
    path = tmp_path / "optimizer-baseline.json"
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


def test_optimizer_probes_methods_allocates_and_trains_final_candidate(
    tmp_path,
) -> None:
    pytest.importorskip("numpy")
    baseline = _baseline(tmp_path)
    examples = (
        TrainingExample(
            example_id="optimizer-example",
            prompt="answer",
            response="target",
            source_ref="optimizer:test",
        ),
    )
    suite = DevelopmentalEvalSuite(
        suite_id="optimizer-development",
        cases=(
            DevelopmentalEvalCase(
                case_id="target-answer",
                prompt="answer",
                required_terms=("target",),
                forbidden_terms=("baseline",),
                max_output_tokens=6,
                seed=0,
            ),
        ),
    )
    final_path = tmp_path / "optimized-final.json"
    mandatory = (
        TrainingMethod.SUPERVISED_INSTRUCTION,
        TrainingMethod.CAUSAL_LANGUAGE_MODELING,
        TrainingMethod.SELF_SUPERVISED_SPAN,
    )

    result = optimize_training_mix(
        examples=examples,
        baseline_path=baseline,
        suite=suite,
        work_dir=tmp_path,
        final_output_path=final_path,
        model_id="optimized-final",
        requested_methods=mandatory,
        allocation_policy=TrainingAllocationPolicy(
            max_repeat_per_method=3,
            max_total_repeats=7,
            mandatory_methods=mandatory,
        ),
        optimization_policy=TrainingOptimizationPolicy(
            max_probes=3,
            probe_epochs=1,
            probe_gradient_accumulation_steps=1,
            final_gradient_accumulation_steps=2,
            cleanup_probe_artifacts=True,
        ),
        hidden_size=8,
        final_epochs=1,
        learning_rate=0.03,
        max_vocab=64,
        max_document_tokens=64,
        seed=41,
        temperature=0.7,
    )

    assert final_path.is_file()
    assert result.probed_methods == mandatory
    assert len(result.reports) == 3
    assert all(report.attribution_verified for report in result.reports)
    assert all(
        report.production_authority is False
        for report in result.reports
    )
    assert {
        item.method for item in result.allocation.method_weights
    } == set(mandatory)
    assert result.final_receipt["training_mode"] == "multi_method"
    assert result.final_receipt["gradient_accumulation_steps"] == 2
    assert len(result.optimization_digest) == 64
    assert result.as_dict()["production_authority"] is False
    assert not list(tmp_path.glob(".probe-*.json"))


def test_optimizer_refuses_to_overwrite_baseline(tmp_path) -> None:
    pytest.importorskip("numpy")
    baseline = _baseline(tmp_path)
    examples = (
        TrainingExample(
            example_id="overwrite-check",
            prompt="answer",
            response="target",
        ),
    )
    suite = DevelopmentalEvalSuite(
        suite_id="overwrite-check",
        cases=(
            DevelopmentalEvalCase(
                case_id="case",
                prompt="answer",
                required_terms=("target",),
            ),
        ),
    )

    from skeleton.ai.runtime.inference.training_optimizer import (
        TrainingOptimizationError,
    )

    with pytest.raises(
        TrainingOptimizationError,
        match="cannot overwrite baseline",
    ):
        optimize_training_mix(
            examples=examples,
            baseline_path=baseline,
            suite=suite,
            work_dir=tmp_path,
            final_output_path=baseline,
            model_id="overwrite-denied",
            requested_methods=(
                TrainingMethod.SUPERVISED_INSTRUCTION,
                TrainingMethod.CAUSAL_LANGUAGE_MODELING,
                TrainingMethod.SELF_SUPERVISED_SPAN,
            ),
            hidden_size=8,
            final_epochs=1,
            max_vocab=64,
            max_document_tokens=64,
        )
