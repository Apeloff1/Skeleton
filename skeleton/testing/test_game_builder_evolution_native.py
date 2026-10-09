"""End-to-end original historical practice -> authentic native-source integration."""
from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.ai.game_builder.evolution_archive import GameEvolutionError
from skeleton.ai.game_builder.evolution_native_sources import (
    compile_evolution_native_sources, export_evolution_native_sources,
)
from skeleton.ai.game_builder.evolution_practice import EvolutionPractice, EvolutionPracticePack
from skeleton.ai.game_builder.playable_simulation import demonstrate_solvable
from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource


def _pack(*, width: int = 17):
    intent = GameBuildIntent(
        project_id="evolve-original", title="Moon Atlas",
        subtitle="Real native practice games", seed=2981,
        width=width, height=15, levels=2,
        collectibles_per_level=2, hazards_per_level=2, starting_health=3,
    )
    original = generate_playable_world(intent, authorized=True)
    original_digest = original.digest
    destinations = ("sinclair_zx81", "nintendo_game_boy", "linux_desktop", "macos_modern")
    demos = []
    for number, platform in enumerate(destinations, 1):
        stage_intent = replace(intent, seed=intent.seed + number)
        game = generate_playable_world(stage_intent, authorized=True)
        replay = demonstrate_solvable(game, authorized=True)
        demos.append(EvolutionPractice(
            stage_number=number, intended_platform_id=platform,
            original_world_id=original_digest,
            game_world=game, winning_replay=replay,
            design_signal_goals=("better_graphics",), hardware_profile="historical_reference",
        ))
    pack = EvolutionPracticePack(intent.project_id, original_digest, tuple(demos))
    source = HomebrewSource(
        project_id=intent.project_id, platform_id="bandai_wonderswan",
        rights_basis="project_owned", evidence_sha256="a" * 64,
        creative_identity=("original grid navigation", "ink maze", "evolving cartography"),
    )
    return pack, source


def test_evolution_game_generates_3_real_native_source_projects_and_1_design_only(tmp_path):
    pack, source = _pack()
    result = compile_evolution_native_sources(pack, source, authorized=True)
    again = compile_evolution_native_sources(pack, source, authorized=True)
    assert result == again
    summary = result.summary()
    assert summary["native_source_stages"] == 3
    assert summary["design_only_stages"] == 1
    assert summary["budget_incompatible_stages"] == 0
    assert summary["compiled_binaries"] == 0
    assert summary["hardware_verified"] == 0
    assert [p.status for p in result.stages] == [
        "design_only", "native_source_ready",
        "native_source_ready", "native_source_ready",
    ]
    assert "rgbds" in result.stages[1].source_kind
    assert "native_sdl2_source_project" == result.stages[2].source_kind
    assert all(row.replay_digest == p.winning_replay.digest
               for row, p in zip(result.stages, pack.demos))
    out = export_evolution_native_sources(result, tmp_path / "evolution", authorized=True)
    assert (out / "stage-02-nintendo_game_boy" / "main.asm").is_file()
    assert (out / "stage-03-linux_desktop" / "game.c").is_file()
    assert (out / "stage-04-macos_modern" / "CMakeLists.txt").is_file()
    assert not (out / "stage-01-sinclair_zx81").exists()
    assert (out / "evolution-native-manifest.json").is_file()
    with pytest.raises(FileExistsError):
        export_evolution_native_sources(result, out, authorized=True)


def test_overbudget_dmg_stage_is_distinct_from_design_only_and_never_silently_cropped():
    pack, source = _pack(width=21)
    result = compile_evolution_native_sources(pack, source, authorized=True)
    assert [stage.status for stage in result.stages] == [
        "design_only", "budget_incompatible",
        "native_source_ready", "native_source_ready",
    ]
    assert result.summary()["budget_incompatible_stages"] == 1
    assert result.stages[1].project is None
    assert result.stages[1].source_digest is None


def test_native_evolution_pack_refuses_cross_project_or_forged_claims(tmp_path):
    pack, source = _pack()
    with pytest.raises(PermissionError):
        compile_evolution_native_sources(pack, source, authorized=False)
    with pytest.raises(GameEvolutionError, match="rights project"):
        compile_evolution_native_sources(pack, replace(source, project_id="elsewhere"), authorized=True)
    altered = replace(pack.demos[1], native_binary_built=True)
    with pytest.raises(GameEvolutionError, match="forged hardware"):
        compile_evolution_native_sources(
            replace(pack, demos=(*pack.demos[:1], altered, *pack.demos[2:])),
            source, authorized=True,
        )
    source_pack = compile_evolution_native_sources(pack, source, authorized=True)
    with pytest.raises(PermissionError):
        export_evolution_native_sources(source_pack, tmp_path / "denied", authorized=False)
    assert not (tmp_path / "denied").exists()
