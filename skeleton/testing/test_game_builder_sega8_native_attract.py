"""Hardware-native homebrew exhibition/attract mode for authored SMS/GG games.

Tests the actual emitted C route tables rather than trusting source metadata.
The feature replays independently proven original actions; no proprietary
games, BIOS, graphics or learned media are incorporated in its code.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re

import pytest

from skeleton.ai.game_builder.playable_world import GameBuildIntent, generate_playable_world
from skeleton.ai.game_builder.port_planner import HomebrewSource
from skeleton.ai.game_builder.sega_8bit_native_export import compile_native_sega_8bit


_MOVES = {"up": 0, "down": 1, "left": 2, "right": 3}


@pytest.mark.parametrize("target", ("sega_master_system", "sega_game_gear"))
@pytest.mark.parametrize("levels,collectibles", ((1,1),(3,3),(8,6)))
def test_on_cartridge_demo_bytes_are_exact_authoritative_solved_game(target,levels,collectibles):
    world=generate_playable_world(GameBuildIntent(
        project_id="original-sms-gear-demo",
        title="Independently Created Game Evolution",
        subtitle="New authored puzzle solution walkthrough for native cartridges",
        seed=21252 + levels * 5, width=17, height=15,
        levels=levels, collectibles_per_level=collectibles,
        hazards_per_level=4, starting_health=4, theme="forest",
    ),authorized=True)
    rights=HomebrewSource(
        project_id=world.intent.project_id,
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",
        evidence_sha256=world.digest,
        creative_identity=("independent original graphics",
                           "authored hardware game demonstration"),
    )
    project=compile_native_sega_8bit(world,rights,target,authorized=True)
    manifest=json.loads(project.manifest_json)
    route_matches=re.findall(
        r"static const unsigned char demo_(\d+)\[\] = \{([^}]+)\};",
        project.game_c, flags=re.S,
    )
    assert len(route_matches)==levels
    total=0
    for stage,(ordinal,directions) in enumerate(route_matches):
        expected=tuple(_MOVES[move] for move in world.levels[stage].safe_solution)
        actual=tuple(int(x.strip()) for x in directions.split(",") if x.strip())
        assert ordinal==str(stage)
        assert len(actual)==len(expected)
        assert actual==expected
        assert all(0<=move<=3 for move in actual)
        total+=len(actual)
    assert manifest["original_native_solution_attract_mode"] is True
    assert manifest["original_demo_playback_steps"]==total
    assert manifest["original_demo_solution_sha256"] == sha256(json.dumps(
        [list(level.safe_solution) for level in world.levels],
        separators=(",",":"),ensure_ascii=True,
    ).encode("ascii")).hexdigest()
    assert manifest["reference_safe_moves"]==total
    assert manifest["original_demo_chord_frames"]==25
    assert manifest["original_demo_uses_identical_game_rules"] is True
    assert manifest["original_demo_autostart"] is False
    assert manifest["original_demo_external_content"] is False
    for control in (
        "PORT_A_KEY_1 | PORT_A_KEY_2", "reset_original_run",
        "original_demo_lengths", "original_demo_routes",
        "if (demo_active && pressed)", "if (level_index!=old_level) demo_step=0",
        "if (won || lost) demo_active=0",
    ):
        assert control in project.game_c
    assert "__DEMO_ROUTES__" not in project.game_c
    assert "__DEMO_POINTERS__" not in project.game_c
    assert "__DEMO_LENGTHS__" not in project.game_c
    assert project == compile_native_sega_8bit(world,rights,target,authorized=True)


def test_original_native_demo_disallows_wrong_rights_identity():
    world=generate_playable_world(GameBuildIntent(
        project_id="an-original-puzzle",
        title="Original Level Demonstration",subtitle="Authored new homebrew",
        seed=1042,width=9,height=9,levels=1,collectibles_per_level=2,
        hazards_per_level=1,
    ),authorized=True)
    rights=HomebrewSource(
        project_id="another-game",
        platform_id="bandai_wonderswan",
        rights_basis="project_owned",evidence_sha256=world.digest,
        creative_identity=("independent art","original mechanics"),
    )
    with pytest.raises(ValueError,match="identity mismatch"):
        compile_native_sega_8bit(world,rights,"sega_game_gear",authorized=True)
