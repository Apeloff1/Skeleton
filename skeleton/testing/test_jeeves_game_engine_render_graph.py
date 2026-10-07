from __future__ import annotations

import json

import pytest

from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_modern import (
    MODERN_ERAS,
    ModernEngineLab,
    create_modern_machine,
    modern_hardware,
)
from skeleton.jeeves.game_engine_render_graph import (
    EXTERNAL_RESOURCES,
    RENDER_GRAPHS,
    RenderGraphExecutor,
    RenderGraphPass,
    RenderGraphSpec,
    execute_render_graph,
    render_graph_spec,
)


@pytest.mark.parametrize(
    "era",
    MODERN_ERAS,
)
def test_every_modern_era_has_valid_canonical_render_graph(
    era: EngineEra,
) -> None:
    spec = render_graph_spec(
        era
    )
    hardware = modern_hardware(
        era
    )

    assert spec.era is era
    assert (
        tuple(
            item.name
            for item in spec.passes
        )
        == hardware.render_passes
    )
    assert (
        spec.final_resource
        == "display"
    )
    assert (
        set(EXTERNAL_RESOURCES)
        <= {
            resource
            for item in spec.passes
            for resource
            in (
                item.reads
                + item.writes
            )
        }
        | set(EXTERNAL_RESOURCES)
    )


def test_canonical_graph_catalog_exactly_matches_modern_eras() -> None:
    assert set(
        RENDER_GRAPHS
    ) == set(
        MODERN_ERAS
    )


def test_graph_rejects_read_before_write() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="uninitialized",
    ):
        RenderGraphSpec(
            EngineEra.HD,
            (
                RenderGraphPass(
                    "bad",
                    (
                        "missing_resource",
                    ),
                    (
                        "display",
                    ),
                    "graphics",
                ),
            ),
            "display",
        )


def test_graph_rejects_same_resource_read_write_alias() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="read and write",
    ):
        RenderGraphPass(
            "alias",
            (
                "hdr",
            ),
            (
                "hdr",
            ),
            "graphics",
        )


def test_graph_rejects_missing_final_resource_write() -> None:
    with pytest.raises(
        GameEngineLabError,
        match="never writes final",
    ):
        RenderGraphSpec(
            EngineEra.HD,
            (
                RenderGraphPass(
                    "only",
                    (
                        "instances",
                    ),
                    (
                        "intermediate",
                    ),
                    "graphics",
                ),
            ),
            "display",
        )


@pytest.mark.parametrize(
    "era",
    MODERN_ERAS,
)
def test_render_graph_execution_is_bit_stable(
    era: EngineEra,
) -> None:
    kwargs = {
        "instances": (
            (
                1,
                2,
                3,
                4.5,
                0,
            ),
            (
                2,
                1,
                0,
                12.0,
                1,
            ),
        ),
        "frame_constants": {
            "tick": 7,
            "viewport": (
                1920,
                1080,
            ),
        },
        "streaming_state": (
            (0, 0),
            (1, 0),
        ),
    }

    first = execute_render_graph(
        era,
        **kwargs,
    )
    second = execute_render_graph(
        era,
        **kwargs,
    )

    assert first == second
    assert len(
        first.final_digest
    ) == 64
    assert len(
        first.graph_digest
    ) == 64
    assert (
        first.pass_names
        == modern_hardware(
            era
        ).render_passes
    )


def test_render_graph_evidence_changes_when_instances_change() -> None:
    base = execute_render_graph(
        EngineEra.MODERN,
        instances=(
            (
                1,
                1,
                1,
                5.0,
                0,
            ),
        ),
        frame_constants={
            "tick": 0,
        },
        streaming_state=(
            (0, 0),
        ),
    )
    changed = execute_render_graph(
        EngineEra.MODERN,
        instances=(
            (
                1,
                1,
                1,
                5.0,
                0,
            ),
            (
                2,
                2,
                1,
                8.0,
                1,
            ),
        ),
        frame_constants={
            "tick": 0,
        },
        streaming_state=(
            (0, 0),
        ),
    )

    assert (
        base.graph_digest
        != changed.graph_digest
    )
    assert (
        base.final_digest
        != changed.final_digest
    )


def test_render_graph_evidence_changes_with_frame_constants() -> None:
    first = execute_render_graph(
        EngineEra.HD,
        instances=(),
        frame_constants={
            "tick": 1,
        },
        streaming_state=(),
    )
    second = execute_render_graph(
        EngineEra.HD,
        instances=(),
        frame_constants={
            "tick": 2,
        },
        streaming_state=(),
    )

    assert first != second
    assert (
        first.final_digest
        != second.final_digest
    )


def test_required_render_pass_cannot_be_disabled() -> None:
    executor = RenderGraphExecutor(
        render_graph_spec(
            EngineEra.MODERN
        )
    )

    with pytest.raises(
        GameEngineLabError,
        match="required",
    ):
        executor.execute(
            instances=(),
            frame_constants={},
            streaming_state=(),
            disabled_passes=(
                "lighting",
            ),
        )


def test_unknown_disabled_render_pass_fails_closed() -> None:
    executor = RenderGraphExecutor(
        render_graph_spec(
            EngineEra.HD
        )
    )

    with pytest.raises(
        GameEngineLabError,
        match="unknown",
    ):
        executor.execute(
            instances=(),
            frame_constants={},
            streaming_state=(),
            disabled_passes=(
                "imaginary",
            ),
        )


@pytest.mark.parametrize(
    "era",
    MODERN_ERAS,
)
def test_modern_machine_frame_carries_executed_render_graph(
    era: EngineEra,
) -> None:
    machine = create_modern_machine(
        era
    )

    frame = machine.step()

    assert len(
        frame.render_graph_digest
    ) == 64
    assert len(
        frame.final_image_digest
    ) == 64
    assert (
        frame.passes
        == tuple(
            item.name
            for item in render_graph_spec(
                era
            ).passes
        )
    )


def test_modern_frame_graph_changes_as_simulation_advances() -> None:
    machine = create_modern_machine(
        EngineEra.MODERN
    )

    first = machine.step()
    second = machine.step()

    assert (
        first.render_graph_digest
        != second.render_graph_digest
    )
    assert (
        first.final_image_digest
        != second.final_image_digest
    )


def test_render_graph_manifest_corruption_is_detected_and_repaired() -> None:
    lab = ModernEngineLab()
    sandbox = lab.create(
        EngineEra.NEXT
    )
    path = (
        "engine/render_graph.json"
    )
    document = json.loads(
        sandbox.tree.read(
            path
        )
    )
    document[
        "final_resource"
    ] = "not_display"
    broken = sandbox.apply(
        (
            SandboxPatch(
                path,
                json.dumps(
                    document
                ),
                sandbox.tree.file_digest(
                    path
                ),
            ),
        )
    )

    before = lab.evaluate(
        broken
    )

    assert not before.passed
    assert (
        "render_graph"
        in before.failed
        or "file_tree"
        in before.failed
    )

    result = (
        lab.adversarial_improve(
            broken
        )
    )

    assert result.promoted
    assert result.report.passed
    assert (
        json.loads(
            result.sandbox.tree.read(
                path
            )
        )
        == render_graph_spec(
            EngineEra.NEXT
        ).document()
    )
