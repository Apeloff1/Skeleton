"""Original Master System and Game Gear native-source generation contracts.

These tests verify actual authored Z80 game *source* and rights envelopes.
They deliberately never misreport native ROM execution or licensing.
"""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.sega_8bit_native_export import (
    Sega8BitNativeError, compile_native_sega_8bit, export_native_sega_8bit,
)
from skeleton.ai.game_builder.native_game_cli import _NATIVE, build_game


def _world(*, seed=73911, width=17, height=15, levels=3):
    return generate_playable_world(GameBuildIntent(
        project_id="original-sega-8bit-lab",title="Independently Authored Stardust Maze",
        subtitle="Original Z80 hardware game",seed=seed,width=width,height=height,
        levels=levels,collectibles_per_level=3,hazards_per_level=4,
        starting_health=4,theme="space",
    ),authorized=True)


def _rights(world):
    return HomebrewSource(
        project_id=world.intent.project_id,platform_id="bandai_wonderswan",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("unique own world", "independently designed stage system"),
    )


@pytest.mark.parametrize("target,extension,library,define",(
    ("sega_master_system","sms","SMSlib.lib",""),
    ("sega_game_gear","gg","SMSlib_GG.lib","-D TARGET_GG"),
))
def test_real_machine_source_implements_controller_vdp_objectives_and_level_state(
    target,extension,library,define,tmp_path
):
    world=_world()
    project=compile_native_sega_8bit(world,_rights(world),target,authorized=True)
    assert project==compile_native_sega_8bit(world,_rights(world),target,authorized=True)
    assert project.content_digest and len(project.content_digest)==64
    assert not project.cartridge_compiled and not project.emulator_playthrough_verified
    assert f'skeleton-original.{extension}' in project.makefile
    assert library in project.makefile
    if define: assert define in project.makefile
    for expected in (
        "SMS_loadTiles(original_tiles", "SMS_setTileatXY", "SMS_waitForVBlank()",
        "SMS_getKeysStatus()", "PORT_A_KEY_UP", "PORT_A_KEY_DOWN",
        "PORT_A_KEY_LEFT", "PORT_A_KEY_RIGHT", "static void advance",
        "static void draw_hud", "static void load_level", "score+=10",
        "end_game(0)", "end_game(1)", "stage_0[MAP_SIZE]",
        "stage_1[MAP_SIZE]", "stage_2[MAP_SIZE]",
        "SMS_EMBED_SEGA_ROM_HEADER(0,0)",
    ):
        assert expected in project.game_c
    assert not any(marker in project.game_c for marker in (
        "__TILES__","__MAPS__","__LEVELS__","__LEFT__","__TARGET__",
    ))
    manifest=json.loads(project.manifest_json)
    assert manifest["platform"]==target
    assert manifest["world_digest"]==world.digest
    assert manifest["levels"]==len(world.levels)
    assert manifest["reference_safe_moves"]==sum(len(l.safe_solution) for l in world.levels)
    assert manifest["binary_compiled"] is False
    assert manifest["emulator_playthrough_verified"] is False
    assert manifest["physical_hardware_verified"] is False
    assert manifest["distribution_licensed"] is False
    assert manifest["release_approved"] is False
    assert manifest["third_party_game_or_firmware_redistributed"] is False
    folder=export_native_sega_8bit(project,tmp_path/target,authorized=True)
    assert {x.name for x in folder.iterdir()}=={"game.c","Makefile","manifest.json"}
    with pytest.raises(FileExistsError):
        export_native_sega_8bit(project,folder,authorized=True)


@pytest.mark.parametrize("width,height,levels",((9,9,1),(17,15,3),(19,15,8)))
def test_game_gear_original_solvable_levels_fit_visible_viewport(width,height,levels):
    world=_world(width=width,height=height,levels=levels)
    p=compile_native_sega_8bit(world,_rights(world),"sega_game_gear",authorized=True)
    assert "#define LEFT 6" in p.game_c
    assert "#define TOP 5" in p.game_c
    assert "#define HUD_Y 3" in p.game_c
    assert p.game_c.count("static const unsigned char stage_")==levels
    assert f"#define WIDTH {width}" in p.game_c


@pytest.mark.parametrize("width,height",((31,21),(19,17)))
def test_master_system_uses_full_256x192_envelope(width,height):
    world=_world(width=width,height=height)
    p=compile_native_sega_8bit(world,_rights(world),"sega_master_system",authorized=True)
    assert "#define LEFT 0" in p.game_c and "#define TOP 2" in p.game_c


def test_reject_oversized_game_gear_and_mismatch_and_cannot_forge_authority(tmp_path):
    world=_world()
    rights=_rights(world)
    with pytest.raises(PermissionError):
        compile_native_sega_8bit(world,rights,"sega_game_gear",authorized=False)
    with pytest.raises(Sega8BitNativeError,match="identity mismatch"):
        compile_native_sega_8bit(world,replace(rights,project_id="other"),"sega_game_gear",authorized=True)
    with pytest.raises(Sega8BitNativeError,match="unsupported"):
        compile_native_sega_8bit(world,rights,"sega_megadrive",authorized=True)
    tall=_world(height=17)
    with pytest.raises(Sega8BitNativeError,match="screen tile budget"):
        compile_native_sega_8bit(tall,_rights(tall),"sega_game_gear",authorized=True)
    wide=_world(width=21)
    with pytest.raises(Sega8BitNativeError,match="screen tile budget"):
        compile_native_sega_8bit(wide,_rights(wide),"sega_game_gear",authorized=True)
    p=compile_native_sega_8bit(world,rights,"sega_master_system",authorized=True)
    with pytest.raises(PermissionError):
        export_native_sega_8bit(p,tmp_path/"forbidden",authorized=False)
    with pytest.raises(Sega8BitNativeError,match="bytes changed"):
        export_native_sega_8bit(replace(p,game_c=p.game_c+"\n"),tmp_path/"stale",authorized=True)
    assert not (tmp_path/"forbidden").exists()
    assert not (tmp_path/"stale").exists()


def test_independent_original_seed_changes_native_level_bytes():
    a,b=_world(),_world(seed=73925)
    sms1=compile_native_sega_8bit(a,_rights(a),"sega_master_system",authorized=True)
    sms2=compile_native_sega_8bit(b,_rights(b),"sega_master_system",authorized=True)
    gear=compile_native_sega_8bit(a,_rights(a),"sega_game_gear",authorized=True)
    assert sms1.content_digest!=sms2.content_digest
    assert sms1.game_c!=sms2.game_c
    assert sms1.content_digest!=gear.content_digest
    assert gear.target_platform_id=="sega_game_gear"


@pytest.mark.parametrize("target",("sega_master_system","sega_game_gear"))
def test_native_cli_and_portfolio_registration_export_real_target(target,tmp_path):
    assert target in _NATIVE
    evidence=tmp_path/"own-work.txt"
    evidence.write_text("independently written homebrew game source\n",encoding="utf-8")
    report=build_game(
        target=target,basis="bandai_wonderswan",
        project_id="own-source",title="Unique Pixel Galaxy",seed=1987,
        width=17,height=15,levels=2,collectibles=2,hazards=2,health=3,
        rights_evidence=evidence,
        creative_identity=("my original gameplay","my unique artwork"),
        output=tmp_path/target,authorized=True,
    )
    assert report["target"]==target
    assert report["native_binary_built"] is False
    assert report["emulator_verified"] is False
    assert report["distribution_licensed"] is False
    assert (tmp_path/target/"game.c").is_file()



def test_game_evolution_stages_emit_real_sms_and_gear_native_source(tmp_path):
    from skeleton.ai.game_builder.evolution_practice import (
        EvolutionPractice, EvolutionPracticePack,
    )
    from skeleton.ai.game_builder.evolution_native_sources import (
        compile_evolution_native_sources, export_evolution_native_sources,
    )
    from skeleton.ai.game_builder.playable_simulation import demonstrate_solvable

    root = _world(seed=44)
    destinations = ("sega_master_system", "sega_game_gear")
    demos = []
    for index, target in enumerate(destinations,1):
        world = _world(seed=44+index)
        demos.append(EvolutionPractice(
            stage_number=index, intended_platform_id=target,
            original_world_id=root.digest, game_world=world,
            winning_replay=demonstrate_solvable(world,authorized=True),
            design_signal_goals=("more_color",),
            hardware_profile="historical_reference",
        ))
    practice = EvolutionPracticePack(root.intent.project_id,root.digest,tuple(demos))
    pack = compile_evolution_native_sources(practice,_rights(root),authorized=True)
    assert pack.summary()["native_source_stages"] == 2
    assert pack.summary()["compiled_binaries"] == 0
    assert [s.status for s in pack.stages] == ["native_source_ready","native_source_ready"]
    output = export_evolution_native_sources(pack,tmp_path/"authored-evolution",authorized=True)
    for i,target in enumerate(destinations,1):
        folder = output/f"stage-{i:02d}-{target}"
        assert (folder/"game.c").is_file()
        assert (folder/"manifest.json").is_file()
        assert json.loads((folder/"manifest.json").read_text())["platform"] == target


def test_historical_gear_port_fails_closed_when_screen_too_small():
    from skeleton.ai.game_builder.evolution_practice import (
        EvolutionPractice, EvolutionPracticePack,
    )
    from skeleton.ai.game_builder.evolution_native_sources import compile_evolution_native_sources
    from skeleton.ai.game_builder.playable_simulation import demonstrate_solvable

    root = _world(seed=66,width=21,height=17)
    demos=[]
    for index,target in enumerate(("sega_game_gear","sega_master_system"),1):
        world=_world(seed=66+index,width=21,height=17)
        demos.append(EvolutionPractice(
            stage_number=index,intended_platform_id=target,
            original_world_id=root.digest,game_world=world,
            winning_replay=demonstrate_solvable(world,authorized=True),
            design_signal_goals=("preserve_originality",),hardware_profile="historical_reference",
        ))
    pack=compile_evolution_native_sources(
        EvolutionPracticePack(root.intent.project_id,root.digest,tuple(demos)),
        _rights(root),authorized=True,
    )
    assert [stage.status for stage in pack.stages] == [
        "budget_incompatible","native_source_ready",
    ]
    assert pack.stages[0].project is None



def test_artifact_must_not_forge_machine_execution_or_release_flags():
    from hashlib import sha256

    world=_world()
    p=compile_native_sega_8bit(world,_rights(world),"sega_game_gear",authorized=True)
    with pytest.raises(Sega8BitNativeError,match="self-certify"):
        replace(p,cartridge_compiled=True)
    with pytest.raises(Sega8BitNativeError,match="self-certify"):
        replace(p,physical_hardware_verified=True)
    meta=json.loads(p.manifest_json)
    meta["release_approved"]=True
    forged_manifest=json.dumps(meta,indent=2,sort_keys=True)+"\\n"
    forged_hash=sha256((p.game_c+"\\0"+p.makefile+"\\0"+forged_manifest).encode()).hexdigest()
    with pytest.raises(Sega8BitNativeError,match="cannot claim release"):
        replace(p,manifest_json=forged_manifest,content_digest=forged_hash)
