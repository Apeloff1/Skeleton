from __future__ import annotations

import json

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_assets import (
    ERA_ASSET_POLICIES,
    AssetCompilerAdversary,
    AssetKind,
    EraAssetCompiler,
    SourceAsset,
    asset_policy,
    attach_asset_build,
    canonical_asset_patches,
    canonical_asset_sources,
    compile_asset_build,
)
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
    SandboxPatch,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)


def test_every_engine_era_has_asset_policy() -> None:
    assert set(
        ERA_ASSET_POLICIES
    ) == set(EngineEra)


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_canonical_asset_pack_compiles_and_attaches_deterministically(
    era: EngineEra,
) -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        era,
        "action_adventure",
    )
    sources = canonical_asset_sources(
        era
    )

    first = compile_asset_build(
        era,
        sources,
    )
    second = compile_asset_build(
        era,
        sources,
    )

    assert first == second
    assert len(
        first.manifest_digest
    ) == 64
    assert first.assets

    attached = attach_asset_build(
        sandbox,
        sources,
    )
    report = (
        AssetCompilerAdversary()
        .evaluate(
            attached,
            sources,
        )
    )

    assert report.passed
    assert report.score == 1.0
    assert {
        "manifest",
        "inventory",
        "reproducibility",
        "integrity",
        "budget",
    } == {
        probe.name
        for probe
        in report.probes
    }


def test_pong_rejects_mesh_assets() -> None:
    compiler = EraAssetCompiler()
    with pytest.raises(
        GameEngineLabError,
        match="unavailable",
    ):
        compiler.compile(
            EngineEra.PONG,
            SourceAsset(
                "mesh",
                AssetKind.MESH,
                triangles=10,
            ),
        )


def test_eight_bit_compiler_clamps_palette_dimension_and_audio() -> None:
    compiler = EraAssetCompiler()
    sprite = compiler.compile(
        EngineEra.EIGHT_BIT,
        SourceAsset(
            "hero",
            AssetKind.SPRITE,
            width=300,
            height=129,
            colors=10_000,
            frames=100,
        ),
    )
    audio = compiler.compile(
        EngineEra.EIGHT_BIT,
        SourceAsset(
            "theme",
            AssetKind.AUDIO,
            sample_rate=96_000,
            channels=8,
            frames=60,
        ),
    )

    assert sprite.width == 64
    assert sprite.height == 64
    assert sprite.colors == 64
    assert sprite.frames == 32
    assert sprite.format == "indexed_2bpp"
    assert audio.sample_rate == 11_025
    assert audio.channels == 4
    assert audio.format == "chiptune"


def test_early_3d_compiler_clamps_mesh_and_texture_envelope() -> None:
    compiler = EraAssetCompiler()
    mesh = compiler.compile(
        EngineEra.EARLY_3D,
        SourceAsset(
            "hero_mesh",
            AssetKind.MESH,
            triangles=100_000,
        ),
    )
    texture = compiler.compile(
        EngineEra.EARLY_3D,
        SourceAsset(
            "hero_tex",
            AssetKind.TEXTURE,
            width=4_000,
            height=3_000,
            colors=100_000_000,
        ),
    )

    assert mesh.triangles == 3_000
    assert mesh.format == "indexed_triangles"
    assert texture.width == 256
    assert texture.height == 256
    assert texture.colors == 65_536
    assert texture.format == "rgb555"


def test_modern_and_next_use_distinct_virtual_asset_formats() -> None:
    compiler = EraAssetCompiler()
    modern = compiler.compile(
        EngineEra.MODERN,
        SourceAsset(
            "world",
            AssetKind.MESH,
            triangles=50_000_000,
        ),
    )
    next_asset = compiler.compile(
        EngineEra.NEXT,
        SourceAsset(
            "world",
            AssetKind.MESH,
            triangles=150_000_000,
        ),
    )

    assert modern.triangles == 10_000_000
    assert modern.format == "meshlet_virtual"
    assert next_asset.triangles == 100_000_000
    assert next_asset.format == "micropoly_cluster"


def test_next_allows_every_semantic_asset_kind() -> None:
    policy = asset_policy(
        EngineEra.NEXT
    )
    assert set(
        policy.allowed
    ) == set(AssetKind)


def test_duplicate_asset_ids_fail_closed() -> None:
    source = SourceAsset(
        "same",
        AssetKind.SPRITE,
    )
    with pytest.raises(
        GameEngineLabError,
        match="unique",
    ):
        EraAssetCompiler().compile_all(
            EngineEra.EIGHT_BIT,
            (
                source,
                source,
            ),
        )


def test_compiled_pack_fails_when_era_storage_budget_is_exceeded() -> None:
    sources = tuple(
        SourceAsset(
            f"sprite_{index}",
            AssetKind.SPRITE,
            width=64,
            height=64,
            colors=64,
            frames=32,
        )
        for index in range(11)
    )

    with pytest.raises(
        GameEngineLabError,
        match="storage budget",
    ):
        EraAssetCompiler().compile_all(
            EngineEra.EIGHT_BIT,
            sources,
        )


def test_asset_manifest_tamper_is_detected() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.SIXTEEN_BIT
    )
    sources = canonical_asset_sources(
        EngineEra.SIXTEEN_BIT
    )
    attached = attach_asset_build(
        sandbox,
        sources,
    )
    path = "assets/compiled/manifest.json"
    manifest = json.loads(
        attached.tree.read(path)
    )
    manifest["asset_count"] += 1
    tampered = attached.apply(
        (
            SandboxPatch(
                path,
                json.dumps(
                    manifest,
                    sort_keys=True,
                ),
                attached.tree.file_digest(
                    path
                ),
            ),
        )
    )

    report = (
        AssetCompilerAdversary()
        .evaluate(
            tampered,
            sources,
        )
    )

    assert not report.passed
    assert "manifest" in report.failed


def test_compiled_asset_payload_tamper_is_detected() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.MODERN
    )
    sources = canonical_asset_sources(
        EngineEra.MODERN
    )
    attached = attach_asset_build(
        sandbox,
        sources,
    )
    build = compile_asset_build(
        EngineEra.MODERN,
        sources,
    )
    target = build.assets[0]
    suffix = {
        AssetKind.PRIMITIVE: "prim.json",
        AssetKind.VECTOR: "vec.json",
        AssetKind.SPRITE: "sprite.json",
        AssetKind.TILESET: "tiles.json",
        AssetKind.MESH: "mesh.json",
        AssetKind.TEXTURE: "tex.json",
        AssetKind.MATERIAL: "mat.json",
        AssetKind.AUDIO: "audio.json",
        AssetKind.ANIMATION: "anim.json",
    }[target.kind]
    path = (
        "assets/compiled/"
        + target.asset_id
        + "."
        + suffix
    )
    payload = json.loads(
        attached.tree.read(path)
    )
    payload["format"] = "forged"
    tampered = attached.apply(
        (
            SandboxPatch(
                path,
                json.dumps(
                    payload,
                    sort_keys=True,
                ),
                attached.tree.file_digest(
                    path
                ),
            ),
        )
    )

    report = (
        AssetCompilerAdversary()
        .evaluate(
            tampered,
            sources,
        )
    )

    assert not report.passed
    assert "integrity" in report.failed


def test_asset_attach_preserves_engine_runtime_quality() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.SHADER,
        "immersive_sim",
    )
    attached = attach_asset_build(
        sandbox,
        canonical_asset_sources(
            EngineEra.SHADER
        ),
    )

    assert lab.evaluate(
        attached
    ).passed



def test_jeeves_compiles_and_evaluates_assets_inside_engine_sandbox() -> None:
    jeeves = Jeeves()
    sandbox = jeeves.build_game_engine(
        EngineEra.EIGHT_BIT,
        gameplay_dialect="platformer",
    )
    sources = canonical_asset_sources(
        EngineEra.EIGHT_BIT
    )

    compiled = jeeves.compile_game_assets(
        sandbox,
        sources,
    )
    report = jeeves.evaluate_game_assets(
        compiled,
        sources,
    )

    assert report.passed
    assert (
        "assets/compiled/manifest.json"
        in compiled.tree.files
    )
    assert (
        jeeves.evaluate_game_engine(
            compiled
        ).passed
    )



def test_asset_repair_removes_unexpected_compiled_artifact() -> None:
    lab = ExecutableGameEngineLab()
    sandbox = lab.create(
        EngineEra.EIGHT_BIT
    )
    sources = canonical_asset_sources(
        EngineEra.EIGHT_BIT
    )
    attached = attach_asset_build(
        sandbox,
        sources,
    )
    rogue = attached.apply(
        (
            SandboxPatch(
                "assets/compiled/rogue.sprite.json",
                "{}",
            ),
        )
    )

    before = (
        AssetCompilerAdversary()
        .evaluate(
            rogue,
            sources,
        )
    )
    assert not before.passed
    assert "inventory" in before.failed

    patches = canonical_asset_patches(
        rogue,
        sources,
    )
    repaired = rogue.apply(
        patches
    )
    after = (
        AssetCompilerAdversary()
        .evaluate(
            repaired,
            sources,
        )
    )

    assert after.passed
    assert (
        "assets/compiled/rogue.sprite.json"
        not in repaired.tree.files
    )
