from __future__ import annotations

import pytest

from skeleton.jeeves.game_engine_3d import (
    FixedFunctionMachine,
    ShaderConsoleMachine,
    SoftwareBspMachine,
)
from skeleton.jeeves.game_engine_rendering import (
    RasterConfig,
    RasterPipeline,
    ReferenceRasterizer,
    RenderTriangle,
    RenderVertex,
    clip_triangle,
)


def _triangle(
    object_id: str,
    material: int,
    z: float,
    *,
    size: float = 1.0,
    shader: str = "fixed",
) -> RenderTriangle:
    return RenderTriangle(
        object_id,
        material,
        (
            RenderVertex(
                -size,
                -size,
                z,
            ),
            RenderVertex(
                size,
                -size,
                z,
            ),
            RenderVertex(
                0.0,
                size,
                z,
            ),
        ),
        shader,
    )


def _render(
    pipeline: RasterPipeline,
    triangles,
):
    return ReferenceRasterizer(
        RasterConfig(
            width=64,
            height=48,
            near=0.5,
            far=20.0,
            fov_y_deg=70.0,
            pipeline=pipeline,
        )
    ).render(triangles)


def test_near_plane_clipping_fan_triangulates_crossing_triangle() -> None:
    triangle = RenderTriangle(
        "near_cross",
        1,
        (
            RenderVertex(
                -1.0,
                -1.0,
                0.25,
            ),
            RenderVertex(
                1.0,
                -1.0,
                2.0,
            ),
            RenderVertex(
                0.0,
                1.0,
                2.0,
            ),
        ),
    )

    clipped = clip_triangle(
        triangle,
        0.5,
        10.0,
    )

    assert len(clipped) == 2
    assert all(
        vertex.z >= 0.5
        for piece in clipped
        for vertex in piece.vertices
    )


def test_triangle_fully_behind_near_plane_is_removed() -> None:
    triangle = _triangle(
        "behind",
        1,
        0.25,
    )

    assert clip_triangle(
        triangle,
        0.5,
        10.0,
    ) == ()


def test_painter_pipeline_rasterizes_without_depth_rejection() -> None:
    frame = _render(
        RasterPipeline.PAINTER,
        (
            _triangle(
                "far",
                1,
                6.0,
                size=2.0,
            ),
            _triangle(
                "near",
                2,
                3.0,
                size=1.0,
            ),
        ),
    )

    assert (
        frame.stats.covered_pixels
        > 0
    )
    assert (
        frame.stats.shaded_fragments
        > 0
    )
    assert (
        frame.stats.depth_rejected_fragments
        == 0
    )
    assert (
        frame.stats.overdraw_fragments
        > 0
    )


def test_fixed_pipeline_depth_test_rejects_hidden_fragments() -> None:
    frame = _render(
        RasterPipeline.FIXED,
        (
            _triangle(
                "near",
                2,
                3.0,
                size=1.5,
            ),
            _triangle(
                "far",
                1,
                6.0,
                size=4.0,
            ),
        ),
    )

    assert (
        frame.stats.depth_rejected_fragments
        > 0
    )
    assert (
        frame.stats.min_depth
        is not None
    )
    assert (
        frame.stats.max_depth
        is not None
    )
    assert (
        frame.stats.min_depth
        < frame.stats.max_depth
    )


def test_z_buffer_output_is_submission_order_invariant() -> None:
    near = _triangle(
        "near",
        2,
        3.0,
        size=1.5,
    )
    far = _triangle(
        "far",
        1,
        6.0,
        size=3.0,
    )

    first = _render(
        RasterPipeline.FIXED,
        (
            near,
            far,
        ),
    )
    second = _render(
        RasterPipeline.FIXED,
        (
            far,
            near,
        ),
    )

    assert (
        first.color_digest
        == second.color_digest
    )
    assert (
        first.depth_digest
        == second.depth_digest
    )
    assert (
        first.material_histogram
        == second.material_histogram
    )


def test_fixed_lighting_changes_color_from_unlit_painter() -> None:
    triangle = RenderTriangle(
        "tilted",
        4,
        (
            RenderVertex(
                -1.0,
                -1.0,
                3.0,
            ),
            RenderVertex(
                1.0,
                -1.0,
                4.0,
            ),
            RenderVertex(
                0.0,
                1.0,
                3.0,
            ),
        ),
    )

    painter = _render(
        RasterPipeline.PAINTER,
        (triangle,),
    )
    fixed = _render(
        RasterPipeline.FIXED,
        (triangle,),
    )

    assert (
        painter.color_digest
        != fixed.color_digest
    )


def test_programmable_shader_tint_changes_framebuffer() -> None:
    fixed_triangle = _triangle(
        "hero",
        3,
        4.0,
        size=1.5,
        shader="fixed",
    )
    skinned_triangle = RenderTriangle(
        "hero",
        3,
        fixed_triangle.vertices,
        "skinned",
    )

    fixed = _render(
        RasterPipeline.PROGRAMMABLE,
        (fixed_triangle,),
    )
    skinned = _render(
        RasterPipeline.PROGRAMMABLE,
        (skinned_triangle,),
    )

    assert (
        fixed.color_digest
        != skinned.color_digest
    )
    assert (
        fixed.depth_digest
        == skinned.depth_digest
    )


def test_programmable_fog_changes_far_material_color() -> None:
    near = _render(
        RasterPipeline.PROGRAMMABLE,
        (
            _triangle(
                "near",
                5,
                3.0,
                size=1.5,
            ),
        ),
    )
    far = _render(
        RasterPipeline.PROGRAMMABLE,
        (
            _triangle(
                "far",
                5,
                18.0,
                size=8.0,
            ),
        ),
    )

    assert near.stats.covered_pixels > 0
    assert far.stats.covered_pixels > 0
    assert (
        near.color_digest
        != far.color_digest
    )


def test_reference_rasterization_is_bit_stable() -> None:
    triangles = (
        _triangle(
            "a",
            1,
            3.0,
            size=1.25,
        ),
        _triangle(
            "b",
            2,
            5.0,
            size=2.0,
        ),
    )

    first = _render(
        RasterPipeline.FIXED,
        triangles,
    )
    second = _render(
        RasterPipeline.FIXED,
        triangles,
    )

    assert first == second
    assert len(first.digest) == 64
    assert len(
        first.color_digest
    ) == 64
    assert len(
        first.depth_digest
    ) == 64


def test_early_3d_machine_produces_real_painter_framebuffer() -> None:
    machine = SoftwareBspMachine()

    frame = machine.reference_raster()

    assert (
        frame.stats.covered_pixels
        > 0
    )
    assert (
        frame.stats.rasterized_triangles
        > 0
    )
    assert (
        frame.stats.depth_rejected_fragments
        == 0
    )


def test_fixed_function_machine_produces_depth_buffer_evidence() -> None:
    machine = FixedFunctionMachine()

    frame = machine.reference_raster()

    assert (
        frame.stats.covered_pixels
        > 0
    )
    assert (
        frame.stats.depth_rejected_fragments
        > 0
    )


def test_shader_animation_changes_actual_programmable_pixels() -> None:
    machine = ShaderConsoleMachine()
    before = machine.reference_raster()

    machine.step()
    after = machine.reference_raster()

    assert (
        before.color_digest
        != after.color_digest
    )
    assert (
        before.stats.covered_pixels
        > 0
    )
    assert (
        after.stats.covered_pixels
        > 0
    )


def test_camera_motion_changes_reference_framebuffer_deterministically() -> None:
    first = FixedFunctionMachine()
    baseline = first.reference_raster()
    first.camera = type(
        first.camera
    )(
        1.0,
        0.0,
        0.0,
    )
    moved = first.reference_raster()

    second = FixedFunctionMachine()
    second.camera = type(
        second.camera
    )(
        1.0,
        0.0,
        0.0,
    )

    assert baseline.digest != moved.digest
    assert (
        moved
        == second.reference_raster()
    )



def test_clipping_preserves_programmable_shader_phase() -> None:
    triangle = RenderTriangle(
        "animated",
        7,
        (
            RenderVertex(
                -1.0,
                -1.0,
                0.25,
            ),
            RenderVertex(
                1.0,
                -1.0,
                2.0,
            ),
            RenderVertex(
                0.0,
                1.0,
                2.0,
            ),
        ),
        "skinned",
        0.375,
    )

    clipped = clip_triangle(
        triangle,
        0.5,
        10.0,
    )

    assert clipped
    assert all(
        piece.shader == "skinned"
        and piece.shader_phase
        == pytest.approx(
            0.375
        )
        for piece in clipped
    )
