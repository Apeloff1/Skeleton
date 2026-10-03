from __future__ import annotations

from skeleton.ai.runtime.inference.multiview import (
    CameraCoveragePolicy,
    CameraView,
    build_camera_coverage,
    stratified_camera_subset,
)
from skeleton.ai.runtime.inference.training_methods import (
    MethodWeight,
    TrainingEfficiencyPolicy,
    TrainingExample,
    TrainingMethod,
    TrainingMethodError,
    compile_training_plan,
    compatible_training_methods,
)


def _full_example() -> TrainingExample:
    return TrainingExample(
        example_id="ex-1",
        prompt="Classify the object and explain the evidence.",
        response="It is a red vehicle because the visible body is red.",
        rejected_response="It is a blue boat.",
        teacher_response="A red road vehicle is visible.",
        positive_text="red vehicle",
        negative_text="blue boat",
        retrieval_context="Camera evidence shows a red road vehicle.",
        trajectory="observe -> identify body -> verify color -> answer",
        pseudo_label="red vehicle",
        task_id="visual-grounding",
        reward=1.0,
        difficulty=0.35,
        source_ref="dataset:fixture",
        replay=True,
        camera_view_refs=(
            "camera-view-sha256:" + ("a" * 64),
            "camera-view-sha256:" + ("b" * 64),
        ),
        camera_coverage_digest="c" * 64,
        tags=("vision", "grounding"),
    )


def test_all_nonvisual_training_families_compile_when_fields_are_available() -> None:
    methods = tuple(TrainingMethod)
    plan = compile_training_plan(
        (_full_example(),),
        methods=methods,
        policy=TrainingEfficiencyPolicy(
            deduplicate=False,
            max_documents=128,
            max_total_chars=200_000,
            max_camera_views_per_example=8,
        ),
    )

    assert set(plan.method_counts) == {
        method.value
        for method in TrainingMethod
        if method is not TrainingMethod.CROSS_VIEW_CONSISTENCY
    }
    assert (
        TrainingMethod.CROSS_VIEW_CONSISTENCY.value
        not in plan.method_counts
    )
    assert plan.method_counts[
        TrainingMethod.MULTIVIEW_GROUNDING.value
    ] == 2
    assert plan.method_counts[
        TrainingMethod.REPLAY.value
    ] == 2
    assert len(plan.plan_digest) == 64


def test_missing_optional_signals_skip_only_dependent_methods() -> None:
    example = TrainingExample(
        example_id="minimal",
        prompt="Q",
        response="A",
    )
    plan = compile_training_plan(
        (example,),
        methods=tuple(TrainingMethod),
    )

    assert TrainingMethod.PREFERENCE.value not in plan.method_counts
    assert TrainingMethod.DISTILLATION.value not in plan.method_counts
    assert TrainingMethod.CONTRASTIVE.value not in plan.method_counts
    assert TrainingMethod.REPLAY.value not in plan.method_counts
    assert TrainingMethod.MULTIVIEW_GROUNDING.value not in plan.method_counts
    assert (
        TrainingMethod.CROSS_VIEW_CONSISTENCY.value
        not in plan.method_counts
    )
    assert TrainingMethod.SUPERVISED_INSTRUCTION.value in plan.method_counts
    assert TrainingMethod.CAUSAL_LANGUAGE_MODELING.value in plan.method_counts
    assert TrainingMethod.SELF_SUPERVISED_SPAN.value in plan.method_counts


def test_compiler_is_replay_deterministic() -> None:
    example = _full_example()
    first = compile_training_plan(
        (example,),
        methods=tuple(TrainingMethod),
    )
    second = compile_training_plan(
        (example,),
        methods=tuple(TrainingMethod),
    )
    assert first.plan_digest == second.plan_digest
    assert first.corpus == second.corpus
    assert first.as_dict() == second.as_dict()


def test_dedup_and_budgeting_are_fail_bounded() -> None:
    example = TrainingExample(
        example_id="same",
        prompt="repeat",
        response="repeat",
        replay=True,
    )
    plan = compile_training_plan(
        (example,),
        methods=(
            MethodWeight(
                TrainingMethod.SUPERVISED_INSTRUCTION,
                repeat=4,
            ),
            TrainingMethod.REPLAY,
        ),
        policy=TrainingEfficiencyPolicy(
            deduplicate=True,
            max_documents=2,
            max_total_chars=1_000,
            replay_repeat=4,
            method_repeat_cap=8,
        ),
    )
    assert len(plan.documents) == 2
    assert [item.repeat_ordinal for item in plan.documents] == [0, 1]
    assert plan.dropped_budget_count >= 1


def test_curriculum_order_and_length_bucketing_are_stable() -> None:
    hard = TrainingExample(
        example_id="hard",
        prompt="hard prompt " * 20,
        response="hard answer",
        difficulty=0.9,
    )
    easy = TrainingExample(
        example_id="easy",
        prompt="easy",
        response="easy answer",
        difficulty=0.1,
    )
    plan = compile_training_plan(
        (hard, easy),
        methods=(TrainingMethod.SUPERVISED_INSTRUCTION,),
        policy=TrainingEfficiencyPolicy(
            length_bucket_chars=64,
            curriculum_easy_first=True,
        ),
    )
    assert plan.documents[0].example_id == "easy"


def test_camera_full_sphere_covers_poles_azimuth_roll_and_fov() -> None:
    plan = build_camera_coverage(
        CameraCoveragePolicy(
            azimuth_step_deg=45,
            elevation_step_deg=30,
            roll_step_deg=90,
            fov_degrees=(35.0, 55.0, 85.0),
            max_views=2_048,
        )
    )
    elevations = {view.elevation_deg for view in plan.views}
    azimuths = {
        view.azimuth_deg
        for view in plan.views
        if abs(view.elevation_deg) != 90.0
    }
    rolls = {view.roll_deg for view in plan.views}
    fovs = {view.fov_deg for view in plan.views}

    assert -90.0 in elevations and 90.0 in elevations
    assert azimuths == {
        0.0,
        45.0,
        90.0,
        135.0,
        180.0,
        225.0,
        270.0,
        315.0,
    }
    assert rolls == {0.0, 90.0, 180.0, 270.0}
    assert fovs == {35.0, 55.0, 85.0}
    assert len(plan.references) == len(set(plan.references))
    assert len(plan.coverage_digest) == 64


def test_poles_canonicalize_degenerate_azimuth() -> None:
    first = CameraView(
        azimuth_deg=0,
        elevation_deg=90,
        roll_deg=0,
        fov_deg=55,
    )
    second = CameraView(
        azimuth_deg=180,
        elevation_deg=90,
        roll_deg=0,
        fov_deg=55,
    )
    assert first.reference == second.reference
    assert first.semantic_angle == "top"


def test_stratified_camera_subset_spreads_over_inventory() -> None:
    plan = build_camera_coverage(
        CameraCoveragePolicy(
            azimuth_step_deg=90,
            elevation_step_deg=90,
            roll_step_deg=180,
            fov_degrees=(55.0,),
            max_views=128,
        )
    )
    subset = stratified_camera_subset(plan, limit=5)
    assert len(subset) == 5
    assert len({item.reference for item in subset}) == 5
    assert subset[0].reference != subset[-1].reference


def test_multi_method_builder_trains_compiled_plan(tmp_path) -> None:
    import pytest

    pytest.importorskip("numpy")
    from skeleton.ai.runtime.inference.train import (
        build_multi_method_recurrent_artifact,
    )

    output = tmp_path / "multi-method.json"
    receipt = build_multi_method_recurrent_artifact(
        examples=(_full_example(),),
        output_path=output,
        model_id="multi-method-local",
        methods=tuple(TrainingMethod),
        efficiency_policy=TrainingEfficiencyPolicy(
            deduplicate=True,
            max_documents=128,
            max_total_chars=200_000,
            max_camera_views_per_example=8,
        ),
        hidden_size=8,
        epochs=8,
        learning_rate=0.03,
        max_vocab=64,
        max_document_tokens=96,
        seed=19,
        temperature=0.7,
        early_stopping_patience=1,
        min_relative_improvement=1.0,
    )

    assert output.is_file()
    assert receipt["training_mode"] == "multi_method"
    assert receipt["training_plan"]["plan_digest"]
    assert receipt["training_plan"]["document_count"] >= 10
    assert receipt["epochs"] == 8
    assert 1 <= receipt["epochs_completed"] < 8
    assert receipt["stopped_early"] is True
    assert len(receipt["training_loss_history"]) == receipt["epochs_completed"]
    assert receipt["training_tokens"] > 0
    assert receipt["gradient_accumulation_steps"] == 4
    expected_steps_per_epoch = (
        receipt["training_plan"]["document_count"] + 3
    ) // 4
    assert receipt["optimizer_steps"] == (
        expected_steps_per_epoch * receipt["epochs_completed"]
    )
    assert receipt["optimizer_steps"] < (
        receipt["training_plan"]["document_count"]
        * receipt["epochs_completed"]
    )
    assert set(receipt["training_plan"]["method_counts"]) == {
        method.value
        for method in TrainingMethod
        if method is not TrainingMethod.CROSS_VIEW_CONSISTENCY
    }


def test_full_camera_coverage_feeds_bounded_multiview_training() -> None:
    coverage = build_camera_coverage()
    subset = stratified_camera_subset(coverage, limit=64)
    example = TrainingExample(
        example_id="camera-all-angles",
        prompt="Describe the object consistently across camera views.",
        response="The same object identity must be preserved.",
        source_ref="scene:fixture",
        camera_view_refs=tuple(item.reference for item in subset),
        camera_coverage_digest=coverage.coverage_digest,
        tags=("vision", "multi-view"),
    )
    plan = compile_training_plan(
        (example,),
        methods=(TrainingMethod.MULTIVIEW_GROUNDING,),
        policy=TrainingEfficiencyPolicy(
            max_camera_views_per_example=32,
            max_documents=64,
            max_total_chars=500_000,
        ),
    )

    assert len(coverage.views) > 100
    assert len(subset) == 64
    assert plan.method_counts[
        TrainingMethod.MULTIVIEW_GROUNDING.value
    ] == 32
    refs = {
        item.metadata["camera_view_ref"]
        for item in plan.documents
    }
    assert len(refs) == 32
    assert plan.camera_coverage_digests == (coverage.coverage_digest,)
    assert plan.as_dict()["camera_coverage_digests"] == [
        coverage.coverage_digest
    ]


def test_training_example_rejects_noncanonical_camera_view_identity() -> None:
    import pytest

    with pytest.raises(
        TrainingMethodError,
        match="camera_view_refs must use canonical camera-view-sha256 identity",
    ):
        TrainingExample(
            example_id="bad-camera-ref",
            prompt="Describe the view.",
            response="A stable object.",
            camera_view_refs=("camera-view:mutable-alias",),
        )


def test_compatible_methods_exclude_missing_signal_families() -> None:
    minimal = TrainingExample(
        example_id="compat-minimal",
        prompt="Q",
        response="A",
    )
    compatible = set(compatible_training_methods((minimal,)))

    assert TrainingMethod.SUPERVISED_INSTRUCTION in compatible
    assert TrainingMethod.DENOISING_AUTOENCODING in compatible
    assert TrainingMethod.IMITATION in compatible
    assert TrainingMethod.PREFERENCE not in compatible
    assert TrainingMethod.CONTRASTIVE not in compatible
    assert TrainingMethod.MULTIVIEW_GROUNDING not in compatible
    assert TrainingMethod.REINFORCEMENT_TRACE not in compatible


def test_camera_refs_require_coverage_identity() -> None:
    import pytest

    with pytest.raises(
        TrainingMethodError,
        match="camera_view_refs require camera_coverage_digest",
    ):
        TrainingExample(
            example_id="camera-without-coverage",
            prompt="Describe the view.",
            response="A stable object.",
            camera_view_refs=(
                "camera-view-sha256:" + ("a" * 64),
            ),
        )

    with pytest.raises(
        TrainingMethodError,
        match="camera_coverage_digest requires camera_view_refs",
    ):
        TrainingExample(
            example_id="coverage-without-camera",
            prompt="Describe the view.",
            response="A stable object.",
            camera_coverage_digest="b" * 64,
        )


def test_gradient_accumulation_one_preserves_per_document_updates(
    tmp_path,
) -> None:
    import pytest

    pytest.importorskip("numpy")
    from skeleton.ai.runtime.inference.train import (
        build_multi_method_recurrent_artifact,
    )

    receipt = build_multi_method_recurrent_artifact(
        examples=(
            TrainingExample(
                example_id="acc-one",
                prompt="Q",
                response="A",
            ),
        ),
        output_path=tmp_path / "acc-one.json",
        model_id="acc-one",
        methods=(
            TrainingMethod.SUPERVISED_INSTRUCTION,
            TrainingMethod.CAUSAL_LANGUAGE_MODELING,
        ),
        hidden_size=8,
        epochs=1,
        max_vocab=32,
        max_document_tokens=32,
        gradient_accumulation_steps=1,
    )

    assert receipt["gradient_accumulation_steps"] == 1
    assert receipt["optimizer_steps"] == receipt["training_plan"]["document_count"]
