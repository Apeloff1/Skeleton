"""Regression tests for incremental asset rebuild planning (#807 B007)."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json

import pytest

from skeleton.build.asset_pipeline import (
    AssetPipelineError,
    AssetSpec,
    build_asset_pipeline,
    plan_asset_rebuild,
)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _specs():
    return [
        AssetSpec(
            asset_id="terrain",
            sources={"assets/terrain.png": _digest("terrain-v1")},
            config={"texture-profile": _digest("texture-profile-v1")},
            tools={"texture-compiler": _digest("compiler-v1")},
            packages=("game-assets",),
            cost=3,
        ),
        AssetSpec(
            asset_id="terrain-material",
            sources={"assets/terrain.material": _digest("material-v1")},
            dependencies=("terrain",),
            packages=("game-assets",),
            cost=2,
        ),
        AssetSpec(
            asset_id="ui",
            sources={"assets/ui.png": _digest("ui-v1")},
            tools={"texture-compiler": _digest("compiler-v1")},
            packages=("ui-assets",),
        ),
        AssetSpec(
            asset_id="audio",
            sources={"assets/theme.wav": _digest("audio-v1")},
            config={"audio-profile": _digest("audio-profile-v1")},
            packages=("audio-assets",),
        ),
    ]


def test_source_change_rebuilds_only_asset_and_dependents() -> None:
    pipeline = build_asset_pipeline(_specs())

    plan = plan_asset_rebuild(
        pipeline,
        changed_sources=["assets/terrain.png"],
    )

    assert plan.seed_assets == ("terrain",)
    assert plan.rebuild_assets == ("terrain", "terrain-material")
    assert plan.repackage == ("game-assets",)
    assert plan.ignored_sources == ()
    assert plan.is_noop is False


def test_unrelated_asset_source_does_not_rebuild_other_packages() -> None:
    pipeline = build_asset_pipeline(_specs())

    plan = plan_asset_rebuild(
        pipeline,
        changed_sources=["assets/ui.png"],
    )

    assert plan.rebuild_assets == ("ui",)
    assert plan.repackage == ("ui-assets",)
    assert "terrain" not in plan.rebuild_assets
    assert "audio" not in plan.rebuild_assets


def test_shared_tool_change_rebuilds_all_tool_consumers_and_dependents() -> None:
    pipeline = build_asset_pipeline(_specs())

    plan = plan_asset_rebuild(
        pipeline,
        changed_tools=["texture-compiler"],
    )

    assert set(plan.seed_assets) == {"terrain", "ui"}
    assert set(plan.rebuild_assets) == {"terrain", "terrain-material", "ui"}
    assert plan.repackage == ("game-assets", "ui-assets")


def test_config_change_rebuilds_only_matching_asset_family() -> None:
    pipeline = build_asset_pipeline(_specs())

    plan = plan_asset_rebuild(
        pipeline,
        changed_config=["audio-profile"],
    )

    assert plan.seed_assets == ("audio",)
    assert plan.rebuild_assets == ("audio",)
    assert plan.repackage == ("audio-assets",)


def test_unrelated_changes_are_reported_without_global_rebuild() -> None:
    pipeline = build_asset_pipeline(_specs())

    plan = plan_asset_rebuild(
        pipeline,
        changed_sources=["docs/readme.md"],
        changed_config=["unrelated-config"],
        changed_tools=["unrelated-tool"],
    )

    assert plan.is_noop is True
    assert plan.seed_assets == ()
    assert plan.rebuild_assets == ()
    assert plan.repackage == ()
    assert plan.ignored_sources == ("docs/readme.md",)
    assert plan.ignored_config == ("unrelated-config",)
    assert plan.ignored_tools == ("unrelated-tool",)


def test_no_changes_is_deterministic_noop() -> None:
    pipeline = build_asset_pipeline(_specs())

    left = plan_asset_rebuild(pipeline)
    right = plan_asset_rebuild(pipeline)

    assert left == right
    assert left.is_noop is True
    assert left.rebuild_assets == ()
    assert left.repackage == ()


def test_pipeline_is_order_independent_and_canonical() -> None:
    left = build_asset_pipeline(_specs())
    right = build_asset_pipeline(list(reversed(_specs())))

    assert left.fingerprint == right.fingerprint
    assert left.serialize() == right.serialize()
    assert left.graph.fingerprint == right.graph.fingerprint

    parsed = json.loads(left.serialize())
    assert left.serialize() == json.dumps(
        parsed,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def test_plan_is_order_independent_for_change_inputs() -> None:
    pipeline = build_asset_pipeline(_specs())

    left = plan_asset_rebuild(
        pipeline,
        changed_sources=["assets/ui.png", "assets/terrain.png"],
        changed_tools=["texture-compiler"],
    )
    right = plan_asset_rebuild(
        pipeline,
        changed_sources=["assets/terrain.png", "assets/ui.png"],
        changed_tools=["texture-compiler", "texture-compiler"],
    )

    assert left.plan_fingerprint == right.plan_fingerprint
    assert left.serialize() == right.serialize()


def test_content_digest_change_changes_pipeline_identity() -> None:
    specs = _specs()
    left = build_asset_pipeline(specs)

    changed = list(specs)
    changed[0] = AssetSpec(
        asset_id="terrain",
        sources={"assets/terrain.png": _digest("terrain-v2")},
        config={"texture-profile": _digest("texture-profile-v1")},
        tools={"texture-compiler": _digest("compiler-v1")},
        packages=("game-assets",),
        cost=3,
    )
    right = build_asset_pipeline(changed)

    assert left.fingerprint != right.fingerprint
    assert (
        left.asset_map()["terrain"].fingerprint
        != right.asset_map()["terrain"].fingerprint
    )
    assert (
        left.asset_map()["terrain-material"].fingerprint
        != right.asset_map()["terrain-material"].fingerprint
    )


@pytest.mark.parametrize(
    "spec",
    [
        {
            "id": "bad",
            "sources": {"a": "not-a-digest"},
        },
        {
            "id": "bad",
            "sources": {"a": _digest("a")},
            "packages": ["*"],
        },
        {
            "id": "bad",
            "sources": {"a": _digest("a")},
            "unknown": True,
        },
        {
            "id": "first",
            "asset_id": "second",
            "sources": {"a": _digest("a")},
        },
    ],
)
def test_malformed_specs_fail_closed(spec: dict[str, object]) -> None:
    with pytest.raises(AssetPipelineError):
        build_asset_pipeline([spec])


def test_combined_asset_inputs_respect_graph_input_bound() -> None:
    many_sources = {
        f"assets/source-{index}.bin": _digest(f"source-{index}")
        for index in range(20)
    }
    many_tools = {
        f"tool-{index}": _digest(f"tool-{index}")
        for index in range(13)
    }

    with pytest.raises(AssetPipelineError, match="input count exceeds"):
        build_asset_pipeline(
            [
                AssetSpec(
                    "too-many-inputs",
                    sources=many_sources,
                    tools=many_tools,
                )
            ]
        )


def test_duplicate_asset_id_fails_closed() -> None:
    with pytest.raises(AssetPipelineError, match="duplicate asset id"):
        build_asset_pipeline(
            [
                AssetSpec("same", sources={"a": _digest("a")}),
                AssetSpec("same", sources={"b": _digest("b")}),
            ]
        )


def test_unknown_dependency_and_cycle_fail_closed() -> None:
    with pytest.raises(AssetPipelineError, match="dependency graph is invalid"):
        build_asset_pipeline(
            [
                AssetSpec(
                    "asset",
                    sources={"a": _digest("a")},
                    dependencies=("missing",),
                )
            ]
        )

    with pytest.raises(AssetPipelineError, match="dependency graph is invalid"):
        build_asset_pipeline(
            [
                AssetSpec(
                    "a",
                    sources={"a": _digest("a")},
                    dependencies=("b",),
                ),
                AssetSpec(
                    "b",
                    sources={"b": _digest("b")},
                    dependencies=("a",),
                ),
            ]
        )


def test_dependency_only_derived_asset_is_allowed() -> None:
    pipeline = build_asset_pipeline(
        [
            AssetSpec(
                "source",
                sources={"asset/source.blend": _digest("source")},
                packages=("raw",),
            ),
            AssetSpec(
                "derived",
                dependencies=("source",),
                packages=("runtime",),
            ),
        ]
    )

    plan = plan_asset_rebuild(
        pipeline,
        changed_sources=["asset/source.blend"],
    )

    assert plan.rebuild_assets == ("source", "derived")
    assert plan.repackage == ("raw", "runtime")


def test_empty_or_inputless_pipeline_fails_closed() -> None:
    with pytest.raises(AssetPipelineError, match="requires at least one"):
        build_asset_pipeline([])

    with pytest.raises(AssetPipelineError, match="input or dependency"):
        build_asset_pipeline([AssetSpec("empty")])



def test_rebuild_planning_rejects_tampered_pipeline_identity() -> None:
    pipeline = build_asset_pipeline(_specs())
    tampered = replace(pipeline, fingerprint="0" * 64)

    with pytest.raises(
        AssetPipelineError,
        match="derived fields drifted",
    ):
        plan_asset_rebuild(
            tampered,
            changed_sources=["assets/terrain.png"],
        )


def test_self_consistent_forged_descriptor_fingerprint_fails_closed() -> None:
    pipeline = build_asset_pipeline(_specs())
    first = pipeline.assets[0]
    forged_first = replace(first, fingerprint=_digest("forged-node"))
    assets = (forged_first, *pipeline.assets[1:])
    payload = {
        "schema": pipeline.schema,
        "algorithm": pipeline.algorithm,
        "graph_fingerprint": pipeline.graph.fingerprint,
        "assets": [asset.to_dict() for asset in assets],
    }
    forged_fingerprint = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    forged = replace(
        pipeline,
        assets=assets,
        fingerprint=forged_fingerprint,
    )

    with pytest.raises(
        AssetPipelineError,
        match="derived fields drifted",
    ):
        plan_asset_rebuild(
            forged,
            changed_sources=["assets/terrain.png"],
        )

def test_change_input_must_be_bounded_iterable_not_mapping_or_string() -> None:
    pipeline = build_asset_pipeline(_specs())

    with pytest.raises(AssetPipelineError, match="iterable sequence"):
        plan_asset_rebuild(
            pipeline,
            changed_sources="assets/ui.png",
        )

    with pytest.raises(AssetPipelineError, match="iterable sequence"):
        plan_asset_rebuild(
            pipeline,
            changed_tools={"texture-compiler": True},
        )
