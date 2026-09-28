"""Regression tests for incremental asset invalidation (#807 B007)."""

from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.assets.incremental_pipeline import (
    AssetPipelinePlan,
    AssetPipelineState,
    AssetRecipe,
    AssetSnapshot,
    IncrementalAssetError,
    PackageSnapshot,
    finalize_asset_pipeline,
    parse_asset_pipeline_state,
    plan_asset_pipeline,
)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _recipes(
    *,
    hero_source: str = "hero-source-v1",
    hero_config: str = "hero-config-v1",
    hero_tool: str = "image-tool-v1",
    hero_packages: tuple[str, ...] = ("base",),
) -> tuple[AssetRecipe, ...]:
    return (
        AssetRecipe(
            asset_id="hero",
            source_digest=_sha(hero_source),
            config_digest=_sha(hero_config),
            tool_digest=_sha(hero_tool),
            package_ids=hero_packages,
        ),
        AssetRecipe(
            asset_id="music",
            source_digest=_sha("music-source-v1"),
            config_digest=_sha("music-config-v1"),
            tool_digest=_sha("audio-tool-v1"),
            package_ids=("base", "audio"),
        ),
        AssetRecipe(
            asset_id="menu",
            source_digest=_sha("menu-source-v1"),
            config_digest=_sha("menu-config-v1"),
            tool_digest=_sha("image-tool-v1"),
            package_ids=("ui",),
        ),
    )


def _initial_state() -> AssetPipelineState:
    recipes = _recipes()
    plan = plan_asset_pipeline(recipes)
    return finalize_asset_pipeline(
        plan,
        rebuilt_output_digests={
            "hero": _sha("hero-output-v1"),
            "music": _sha("music-output-v1"),
            "menu": _sha("menu-output-v1"),
        },
    )


def test_initial_plan_rebuilds_all_assets_and_packages() -> None:
    plan = plan_asset_pipeline(_recipes())

    assert plan.rebuild_assets == ("hero", "menu", "music")
    assert plan.reuse_assets == ()
    assert plan.repack_packages == ("audio", "base", "ui")
    assert plan.remove_assets == ()
    assert plan.remove_packages == ()


def test_identical_second_build_is_a_true_noop() -> None:
    state = _initial_state()

    plan = plan_asset_pipeline(_recipes(), previous=state)

    assert plan.rebuild_assets == ()
    assert plan.reuse_assets == ("hero", "menu", "music")
    assert plan.repack_packages == ()
    finalized = finalize_asset_pipeline(
        plan,
        rebuilt_output_digests={},
        previous=state,
    )
    assert finalized == state
    assert finalized.state_digest == state.state_digest


@pytest.mark.parametrize(
    "overrides",
    [
        {"hero_source": "hero-source-v2"},
        {"hero_config": "hero-config-v2"},
        {"hero_tool": "image-tool-v2"},
    ],
)
def test_source_config_or_tool_change_rebuilds_only_affected_asset(
    overrides: dict[str, str],
) -> None:
    state = _initial_state()

    plan = plan_asset_pipeline(_recipes(**overrides), previous=state)

    assert plan.rebuild_assets == ("hero",)
    assert plan.reuse_assets == ("menu", "music")
    assert plan.repack_packages == ("base",)


def test_unrelated_package_is_not_repacked() -> None:
    state = _initial_state()

    plan = plan_asset_pipeline(
        _recipes(hero_source="hero-source-v2"),
        previous=state,
    )

    assert "base" in plan.repack_packages
    assert "audio" not in plan.repack_packages
    assert "ui" not in plan.repack_packages


def test_membership_change_repacks_old_and_new_packages_without_rebuild() -> None:
    state = _initial_state()

    plan = plan_asset_pipeline(
        _recipes(hero_packages=("ui",)),
        previous=state,
    )

    assert plan.rebuild_assets == ()
    assert plan.repack_packages == ("base", "ui")


def test_asset_removal_repackages_members_and_removes_empty_package() -> None:
    state = _initial_state()
    recipes = tuple(recipe for recipe in _recipes() if recipe.asset_id != "menu")

    plan = plan_asset_pipeline(recipes, previous=state)

    assert plan.remove_assets == ("menu",)
    assert plan.remove_packages == ("ui",)
    assert plan.repack_packages == ()


def test_finalize_requires_exact_output_set_for_rebuilt_assets() -> None:
    state = _initial_state()
    plan = plan_asset_pipeline(
        _recipes(hero_source="hero-source-v2"),
        previous=state,
    )

    with pytest.raises(IncrementalAssetError, match="exactly match"):
        finalize_asset_pipeline(
            plan,
            rebuilt_output_digests={},
            previous=state,
        )

    with pytest.raises(IncrementalAssetError, match="exactly match"):
        finalize_asset_pipeline(
            plan,
            rebuilt_output_digests={
                "hero": _sha("hero-output-v2"),
                "menu": _sha("unexpected"),
            },
            previous=state,
        )


def test_finalize_reuses_unaffected_output_digests() -> None:
    state = _initial_state()
    plan = plan_asset_pipeline(
        _recipes(hero_source="hero-source-v2"),
        previous=state,
    )

    updated = finalize_asset_pipeline(
        plan,
        rebuilt_output_digests={"hero": _sha("hero-output-v2")},
        previous=state,
    )
    old_by_id = {row.asset_id: row for row in state.assets}
    new_by_id = {row.asset_id: row for row in updated.assets}

    assert new_by_id["hero"].output_digest == _sha("hero-output-v2")
    assert new_by_id["music"].output_digest == old_by_id["music"].output_digest
    assert new_by_id["menu"].output_digest == old_by_id["menu"].output_digest


def test_state_serialization_round_trips_with_digest_binding() -> None:
    state = _initial_state()

    parsed = parse_asset_pipeline_state(state.serialize())

    assert parsed == state
    payload = json.loads(state.serialize())
    payload["assets"][0]["output_digest"] = _sha("tampered")
    with pytest.raises(IncrementalAssetError, match="state digest mismatch"):
        parse_asset_pipeline_state(payload)


def test_duplicate_json_keys_fail_closed() -> None:
    with pytest.raises(IncrementalAssetError, match="duplicate JSON key"):
        parse_asset_pipeline_state(
            '{"schema":1,"schema":1,"assets":[],"packages":[],"state_digest":"'
            + _sha("x")
            + '"}'
        )


def test_duplicate_recipe_and_package_membership_fail_closed() -> None:
    recipe = _recipes()[0]

    with pytest.raises(IncrementalAssetError, match="duplicate asset recipe"):
        plan_asset_pipeline((recipe, recipe))

    bad = AssetRecipe(
        asset_id="hero",
        source_digest=_sha("source"),
        config_digest=_sha("config"),
        tool_digest=_sha("tool"),
        package_ids=("base", "base"),
    )
    with pytest.raises(IncrementalAssetError, match="duplicate package"):
        plan_asset_pipeline((bad,))


def test_invalid_digest_in_direct_previous_state_fails_closed() -> None:
    state = AssetPipelineState(
        assets=(
            AssetSnapshot(
                asset_id="hero",
                recipe_digest="not-a-digest",
                output_digest=_sha("output"),
            ),
        ),
        packages=(),
    )

    with pytest.raises(IncrementalAssetError, match="recipe_digest"):
        plan_asset_pipeline(_recipes(), previous=state)


def test_previous_package_cannot_reference_unknown_asset() -> None:
    state = AssetPipelineState(
        assets=(
            AssetSnapshot(
                asset_id="hero",
                recipe_digest=_sha("recipe"),
                output_digest=_sha("output"),
            ),
        ),
        packages=(
            PackageSnapshot(
                package_id="base",
                members=(("ghost", _sha("ghost-output")),),
            ),
        ),
    )

    with pytest.raises(IncrementalAssetError, match="unknown asset id"):
        plan_asset_pipeline(_recipes(), previous=state)


def test_tampered_plan_cannot_be_finalized() -> None:
    state = _initial_state()
    valid = plan_asset_pipeline(
        _recipes(hero_source="hero-source-v2"),
        previous=state,
    )
    tampered = AssetPipelinePlan(
        recipes=valid.recipes,
        rebuild_assets=(),
        reuse_assets=("hero", "menu", "music"),
        remove_assets=valid.remove_assets,
        repack_packages=(),
        remove_packages=valid.remove_packages,
        previous_state_digest=valid.previous_state_digest,
    )

    with pytest.raises(IncrementalAssetError, match="plan decisions"):
        finalize_asset_pipeline(
            tampered,
            rebuilt_output_digests={},
            previous=state,
        )
