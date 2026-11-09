"""Genuine 6502 NES authored input evidence: original route and safe rejects."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from scripts.game_builder.native_nes_ci import generate
from scripts.game_builder.nes_6502_controller import (
    NESControllerReplayError, verify_original_nes_first_controller_move,
)
from skeleton.testing.test_game_builder_nes_reproducibility import (
    synthetic_original_nrom,
)


def original(tmp_path):
    source=tmp_path/"generated-original-game"
    evidence=generate(source)
    rom=tmp_path/"original-source.nes"
    image=synthetic_original_nrom()
    rom.write_bytes(image)
    return {
        "compiled_rom":rom,
        "source_directory":source,
        "expected_rom_sha256":sha256(image).hexdigest(),
        "expected_source_sha256":evidence["source_digest"],
    }


def test_original_nes_game_declaration_derives_first_move_from_world(tmp_path):
    fields=original(tmp_path)
    manifest=json.loads(
        (fields["source_directory"]/"manifest.json").read_text(encoding="utf-8")
    )
    button=manifest["original_first_controller_action"]
    start=manifest["original_first_player_spawn"]
    target=manifest["original_first_controller_target"]
    dx,dy={"up":(0,-1),"down":(0,1),"left":(-1,0),"right":(1,0)}[button]
    assert target==[start[0]+dx,start[1]+dy]
    assert 0<=target[0]<manifest["width"]
    assert 0<=target[1]<manifest["height"]
    assert manifest["emulator_verified"] is False
    assert manifest["hardware_verified"] is False
    assert len(manifest["original_stage_zero_bg_sha256"]) == 64


@pytest.mark.parametrize("wrong",[
    "", "f"*64, "0"*64,"MAIN",True,None,
])
def test_synthetic_nes_source_hash_never_forges_authorized_input_provenance(
    tmp_path,wrong,
):
    args=original(tmp_path)
    args["expected_source_sha256"]=wrong
    with pytest.raises(NESControllerReplayError):
        verify_original_nes_first_controller_move(**args)


@pytest.mark.parametrize("bad",[
    "jump","fire",False,123,None,[],{},
])
def test_original_nes_manifest_rejects_unmodeled_synthetic_input_actions(
    tmp_path,bad,
):
    args=original(tmp_path)
    path=args["source_directory"]/"manifest.json"
    data=json.loads(path.read_text(encoding="utf-8"))
    data["original_first_controller_action"]=bad
    path.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(NESControllerReplayError,match="source changed"):
        verify_original_nes_first_controller_move(**args)


@pytest.mark.parametrize("bad_budget",[0,1,49999,850001,True,1.3,None,"50000"])
def test_original_nes_controller_replay_rejects_unbounded_cpu_execution(
    tmp_path,bad_budget,
):
    args=original(tmp_path)
    with pytest.raises(NESControllerReplayError,match="budget"):
        verify_original_nes_first_controller_move(
            **args,instruction_budget=bad_budget,
        )


def test_synthetic_nes_signature_is_not_a_playable_original_game(tmp_path):
    pytest.importorskip("py65")
    args=original(tmp_path)
    with pytest.raises(NESControllerReplayError,match="escaped|budget"):
        verify_original_nes_first_controller_move(
            **args,instruction_budget=50000,
        )


def test_unreviewed_6502_rom_symlink_denied_before_player_button(tmp_path):
    args=original(tmp_path)
    original_rom=args["compiled_rom"]
    link=tmp_path/"swapped-title.nes"
    link.symlink_to(original_rom)
    args["compiled_rom"]=link
    with pytest.raises(ValueError):
        verify_original_nes_first_controller_move(**args)


def test_unreviewed_6502_source_ancestor_link_is_not_accepted(tmp_path):
    args=original(tmp_path)
    real=args["source_directory"]
    link=tmp_path/"swapped-author"
    link.symlink_to(real,target_is_directory=True)
    args["source_directory"]=link
    with pytest.raises(ValueError):
        verify_original_nes_first_controller_move(**args)
