from __future__ import annotations

from io import BytesIO

import pytest

from skeleton.ai.runtime.inference.multiview import (
    CameraCoveragePolicy,
    bind_camera_subset,
    build_camera_coverage,
    stratified_camera_subset,
)
from skeleton.ai.runtime.inference.training_methods import (
    TrainingEfficiencyPolicy,
    TrainingExample,
    TrainingMethod,
    compile_training_plan,
    compatible_training_methods,
)
from skeleton.ai.runtime.inference.visual_learning import (
    VisualLearningError,
    extract_visual_training_observation,
)
from skeleton.ai.runtime.multimodal.intake import (
    Modality,
    MultimodalIntake,
)


def _png_bytes(rgb: tuple[int, int, int]) -> bytes:
    image_module = pytest.importorskip("PIL.Image")
    image = image_module.new("RGB", (8, 8), rgb)
    # Add a deterministic contrasting quadrant so edge/spatial features exist.
    for y in range(4):
        for x in range(4):
            image.putpixel(
                (x, y),
                tuple(255 - value for value in rgb),
            )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _asset(asset_id: str, payload: bytes):
    return MultimodalIntake().sanitize(
        asset_id=asset_id,
        modality=Modality.IMAGE,
        mime_type="image/png",
        payload=payload,
        metadata={
            "filename": asset_id + ".png",
            "width": 8,
            "height": 8,
            "prompt_injection": "ignored metadata",
        },
    )


def _coverage():
    return build_camera_coverage(
        CameraCoveragePolicy(
            azimuth_step_deg=90,
            elevation_step_deg=90,
            roll_step_deg=180,
            fov_degrees=(55.0,),
            max_views=128,
        )
    )


def test_pixel_observation_is_deterministic_and_camera_bound() -> None:
    payload = _png_bytes((220, 30, 30))
    asset = _asset("red-object", payload)
    coverage = _coverage()
    view = stratified_camera_subset(coverage, limit=2)[0]

    first = extract_visual_training_observation(
        asset=asset,
        payload=payload,
        camera_view=view,
    )
    second = extract_visual_training_observation(
        asset=asset,
        payload=payload,
        camera_view=view,
    )

    assert first == second
    assert first.camera_view_ref == view.reference
    assert first.asset_digest == asset.content_digest
    assert len(first.mean_rgb) == 3
    assert len(first.std_rgb) == 3
    assert len(first.luminance_histogram) == 8
    assert len(first.spatial_rgb) == 48
    assert first.reference.startswith("visual-observation-sha256:")
    assert "prompt_injection" not in asset.sanitized_metadata


def test_visual_observation_rejects_bytes_different_from_sanitized_asset() -> None:
    payload = _png_bytes((20, 200, 20))
    asset = _asset("green-object", payload)
    view = stratified_camera_subset(_coverage(), limit=1)[0]

    with pytest.raises(
        VisualLearningError,
        match="bytes differ from sanitized asset digest",
    ):
        extract_visual_training_observation(
            asset=asset,
            payload=_png_bytes((20, 20, 200)),
            camera_view=view,
        )


def test_cross_view_consistency_compiles_two_real_image_observations() -> None:
    coverage = _coverage()
    views = stratified_camera_subset(coverage, limit=2)
    first_payload = _png_bytes((220, 30, 30))
    second_payload = _png_bytes((190, 45, 45))
    first_asset = _asset("object-front", first_payload)
    second_asset = _asset("object-right", second_payload)
    observations = (
        extract_visual_training_observation(
            asset=first_asset,
            payload=first_payload,
            camera_view=views[0],
        ),
        extract_visual_training_observation(
            asset=second_asset,
            payload=second_payload,
            camera_view=views[1],
        ),
    )
    example = TrainingExample(
        example_id="real-two-view-object",
        prompt="What object identity is shared across these views?",
        response="The same red object is present in both camera views.",
        source_ref="visual-fixture:two-view",
        camera_coverage_digest=coverage.coverage_digest,
        camera_selection=bind_camera_subset(coverage, views),
        visual_observations=observations,
        tags=("vision", "cross-view"),
    )

    compatible = set(compatible_training_methods((example,)))
    assert TrainingMethod.MULTIVIEW_GROUNDING in compatible
    assert TrainingMethod.CROSS_VIEW_CONSISTENCY in compatible

    plan = compile_training_plan(
        (example,),
        methods=(
            TrainingMethod.MULTIVIEW_GROUNDING,
            TrainingMethod.CROSS_VIEW_CONSISTENCY,
        ),
        policy=TrainingEfficiencyPolicy(
            max_camera_views_per_example=8,
            max_documents=32,
            max_total_chars=500_000,
        ),
    )

    assert plan.method_counts[
        TrainingMethod.MULTIVIEW_GROUNDING.value
    ] == 2
    assert plan.method_counts[
        TrainingMethod.CROSS_VIEW_CONSISTENCY.value
    ] == 1
    assert set(plan.visual_observation_digests) == {
        item.feature_digest for item in observations
    }
    cross_view = next(
        item
        for item in plan.documents
        if item.method is TrainingMethod.CROSS_VIEW_CONSISTENCY
    )
    assert observations[0].reference in cross_view.text
    assert observations[1].reference in cross_view.text
    assert cross_view.metadata["view_count"] == 2


def test_real_visual_documents_train_local_candidate(tmp_path) -> None:
    pytest.importorskip("numpy")
    pytest.importorskip("PIL.Image")
    from skeleton.ai.runtime.inference.train import (
        build_multi_method_recurrent_artifact,
    )

    coverage = _coverage()
    views = stratified_camera_subset(coverage, limit=2)
    payloads = (
        _png_bytes((210, 40, 40)),
        _png_bytes((180, 55, 55)),
    )
    observations = tuple(
        extract_visual_training_observation(
            asset=_asset(f"train-view-{index}", payload),
            payload=payload,
            camera_view=view,
        )
        for index, (payload, view) in enumerate(
            zip(payloads, views, strict=True)
        )
    )
    example = TrainingExample(
        example_id="visual-train",
        prompt="Identify the shared object across camera angles.",
        response="The views show the same red object.",
        camera_coverage_digest=coverage.coverage_digest,
        camera_selection=bind_camera_subset(coverage, views),
        visual_observations=observations,
        tags=("vision", "identity"),
    )
    output = tmp_path / "visual-local.json"

    receipt = build_multi_method_recurrent_artifact(
        examples=(example,),
        output_path=output,
        model_id="visual-local-candidate",
        methods=(
            TrainingMethod.MULTIVIEW_GROUNDING,
            TrainingMethod.CROSS_VIEW_CONSISTENCY,
            TrainingMethod.SUPERVISED_INSTRUCTION,
        ),
        hidden_size=8,
        epochs=2,
        learning_rate=0.03,
        max_vocab=256,
        max_document_tokens=256,
        gradient_accumulation_steps=2,
        seed=31,
        temperature=0.7,
    )

    assert output.is_file()
    assert receipt["training_mode"] == "multi_method"
    assert receipt["optimizer_steps"] > 0
    assert set(receipt["training_plan"]["visual_observation_digests"]) == {
        item.feature_digest for item in observations
    }
    assert receipt["training_plan"]["method_counts"][
        TrainingMethod.CROSS_VIEW_CONSISTENCY.value
    ] == 1
