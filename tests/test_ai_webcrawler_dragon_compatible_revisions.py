"""Revision reuse only where a genuine homebrew ABI is preserved."""
from __future__ import annotations
from dataclasses import asdict,replace
from hashlib import sha256
import json
import pytest
from skeleton.ai.webcrawler.dragon_compatible_revisions import (
    REVISIONS,COMPATIBILITY,revision_project,
)
from skeleton.ai.webcrawler.dragon_native_targets import CATALOG,target_catalog
from skeleton.ai.webcrawler.dragon_native_projects import EMITTERS,render_native_project
from skeleton.ai.webcrawler.dragon_platform_readiness import readiness_for
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

def _game(target,style="arcade_score_attack"):
    return render_native_project(
        title="Original Dragon Legacy Compatibility",
        target_id=target,style=style,
        candidate_id=sha256((target+style).encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True)

def test_all_11_revisions_have_same_cartridge_abi_and_external_checks():
    assert len(REVISIONS)==len(COMPATIBILITY)==11
    assert len(EMITTERS)==72
    assert len({r.target for r in REVISIONS})==11
    for r in REVISIONS:
        assert CATALOG[r.target].output==CATALOG[r.parent].output==r.output
        assert r.parent not in COMPATIBILITY
        assert r.target in EMITTERS and r.parent in EMITTERS
        assert r.required_test and r.assumption and r.runtime_mode
        assert not readiness_for(r.target).compiler_verified
        assert readiness_for(r.target).source_emitter
    with pytest.raises(ValueError):
        revision_project(
            target_id="commodore_plus4",title="A",style="arcade_score_attack",
            candidate_id="e"*64,mechanics=(Mechanic.MOVEMENT,),
            authorized=True,design=None,renderer=render_native_project)

@pytest.mark.parametrize("revision",REVISIONS,ids=lambda x:x.target)
def test_revision_generates_exact_parent_engine_source_but_new_original_receipt(revision):
    candidate=sha256((revision.target+"arcade_score_attack").encode()).hexdigest()
    parent=render_native_project(
        title="Original Dragon Legacy Compatibility",
        target_id=revision.parent,style="arcade_score_attack",
        candidate_id=candidate,
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    revision_game=render_native_project(
        title="Original Dragon Legacy Compatibility",
        target_id=revision.target,style="arcade_score_attack",
        candidate_id=candidate,
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    again=render_native_project(
        title="Original Dragon Legacy Compatibility",
        target_id=revision.target,style="arcade_score_attack",
        candidate_id=candidate,
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),
        authorized=True,
    )
    assert revision_game==again
    assert revision_game.target_id==revision.target
    assert revision_game.output==parent.output==revision.output
    assert revision_game.digest!=parent.digest
    for path in parent.files:
        if path.startswith(("src/","include/")):
            assert revision_game.files[path]==parent.files[path]
    parent_budget=json.loads(parent.files["dragon-hardware-budget.json"])
    inherited_budget=json.loads(revision_game.files["dragon-parent-hardware-budget.json"])
    assert inherited_budget==parent_budget
    assert "dragon-hardware-budget.json" not in revision_game.files
    receipt=json.loads(revision_game.files["dragon-compatible-revision.json"])
    assert receipt["target"]==revision.target
    assert receipt["parent"]==revision.parent
    assert receipt["source_parent_fingerprint"]==parent.digest
    assert receipt["native_source_reused_without_binary_substitution"]
    assert not receipt["target_compiler_verified"]
    assert not receipt["target_emulator_verified"]
    assert not receipt["target_hardware_verified"]
    manifest=json.loads(revision_game.files["dragon-native-manifest.json"])
    assert manifest["target"]==revision.target
    assert manifest["source_parent"]==revision.parent
    assert manifest["status"]=="source_generated"
    assert not manifest["target_compiler_verified"]
    assert revision.required_test in revision_game.files["README.compatibility.md"]
    assert revision.assumption in revision_game.files["README.compatibility.md"]

def test_dmg_screen_revisions_preserve_real_platform_gameplay_but_gba_does_not():
    rows={r["id"]:r for r in target_catalog()}
    for target in ("game_boy_pocket","game_boy_light"):
        assert "side_scrolling_platformer" in rows[target]["supported_styles"]
        game=_game(target,"side_scrolling_platformer")
        assert "src/main.asm" in game.files
        assert "game_boy_scrolling_platformer" in game.files["dragon-native-manifest.json"]
        assert game.files["dragon-compatible-revision.json"]
    for target in ("game_boy_micro","game_boy_player","psp_go",
                   "nintendo_dsi","nintendo_2ds","atari_130xe"):
        assert "side_scrolling_platformer" not in rows[target]["supported_styles"]
        with pytest.raises(ValueError):
            _game(target,"side_scrolling_platformer")

def test_unsupported_or_licensed_families_are_never_auto_aliased():
    for target in ("famicom_disk_system","sega_32x","amiga_cd32",
                   "nintendo_switch_lite","nintendo_switch_2",
                   "ps5_pro","philips_cdi","apple_iigs"):
        assert target not in COMPATIBILITY
        with pytest.raises((ValueError,PermissionError)):
            _game(target)

def test_unauthorized_compatibility_calls_fail_closed():
    with pytest.raises(PermissionError):
        render_native_project(
            title="Original Dragon Legacy Compatibility",
            target_id="game_boy_pocket",style="arcade_score_attack",
            candidate_id="f"*64,mechanics=(Mechanic.MOVEMENT,),
            authorized=False)
