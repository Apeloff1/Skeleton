"""Cross-port identity, gameplay equality and rights-bound Sega release tests.

Fixtures are synthetic JSON receipts only; they neither forge compiled ROM
execution nor include firmware, game ROMs, or outside expressive material.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path

import pytest

from scripts.game_builder.sega8_port_parity import (
    Sega8PortParityError, verify_ports,
)


WORLD = "a" * 64
REPLAY = "b" * 64
RIGHTS = "c" * 64
TOOLCHAIN = "533ae572c897cf44f1da865013ebf690134301a3"
EXTS = {"sega_master_system": "sms", "sega_game_gear": "gg"}


def _fixtures(tmp_path: Path) -> dict[str, dict[str, Path]]:
    files: dict[str, dict[str, Path]] = {}
    for index, (target, ext) in enumerate(EXTS.items(), 1):
        root = tmp_path / ("original-sega8-source-and-hash-evidence-" + target)
        source = root / "output" / target
        source.mkdir(parents=True)
        content = {
            "manifest": {
                "schema": "skeleton.game_builder.native_sega8_source.v1",
                "platform": target, "target_rom_suffix": ext,
                "project_id": "original-legal-homebrew",
                "title": "Original Constellation Challenge",
                "world_digest": WORLD,
                "reference_safe_replay_digest": REPLAY,
                "source_rights_evidence_sha256": RIGHTS,
                "original_color_theme": "space",
                "original_native_solution_attract_mode": True,
                "original_demo_playback_steps": 256,
                "original_demo_compressed_rom_bytes": 65,
                "original_demo_direction_encoding": "2bit_lsb_first:0=up,1=down,2=left,3=right",
                "original_demo_solution_sha256": "9"*64,
                "original_demo_uses_identical_game_rules": True,
                "original_demo_autostart": False,
                "original_demo_external_content": False,
                "levels": 3, "width": 17, "height": 15,
                "binary_compiled": False, "emulator_playthrough_verified": False,
                "physical_hardware_verified": False, "release_approved": False,
                "distribution_licensed": False,
                "third_party_game_or_firmware_redistributed": False,
            },
            "compile": {
                "schema": "skeleton.game_builder.sega8_actual_compilation_evidence.v1",
                "target": target,
                "real_rom_structure_verified": True,
                "rom_header_checksum_verified": True,
                "original_world_digest": WORLD,
                "reference_safe_replay_digest": REPLAY,
                "source_rights_evidence_sha256": RIGHTS,
                "source_sha256": str(index) * 64,
                "toolchain_revision": TOOLCHAIN,
                "rom_sha256": str(index + 3) * 64,
                "physical_hardware_verified": False,
                "distribution_licensed": False, "release_approved": False,
                "native_rom_compiled": False,
                "emulator_playthrough_verified": False,
                "rights_independently_verified": False,
            },
            "host": {
                "schema": "skeleton.game_builder.sega8_c_gameplay_differential.v1",
                "target": target,
                "native_game_c_compiled_and_executed_on_host": True,
                "all_level_completion_verified": True,
                "original_score_and_screen_state_verified": True,
                "original_companion_rank_progression_verified": True,
                "original_native_solution_attract_mode_host_verified": True,
                "original_demo_controller_actions_verified": 256,
                "original_demo_screen_trace_sha256": "7"*64,
                "source_content_digest": str(index) * 64,
                "world_digest": WORLD, "original_controller_actions_verified": 256,
                "original_levels_verified": 3,
                "authoritative_reference_sha256": str(index + 6) * 64,
                "full_console_emulator_playthrough_verified": False,
                "physical_hardware_verified": False, "release_approved": False,
                "native_z80_rom_executed": False,
                "rights_independently_verified": False,
            },
            "boot": {
                "schema": "skeleton.game_builder.sega8_real_z80_boot_smoke.v1",
                "target": target,
                "rom_sha256": str(index + 3) * 64,
                "hardware_boot_smoke_verified": True,
                "game_hero_rendered": True,
                "original_companion_rendered": True,
                "zero_score_hud_verified": True,
                "entire_game_playthrough_verified": False,
                "independent_cycle_exact_emulator_verified": False,
                "physical_hardware_verified": False,
                "distribution_licensed": False,
                "release_approved": False,
            },
        }

        # Synthetic JSON fixtures exercise cross-port gate behavior only.
        # They are never an attestation of an actually executed Z80 game.
        content["native_route"] = {
            "schema": "skeleton.game_builder.sega8_actual_z80_gameplay_replay.v1",
            "target": target,
            "rom_sha256": str(index+3)*64,
            "source_content_digest": str(index)*64,
            "original_world_digest": WORLD,
            "original_route_sha256": str(index+6)*64,
            "original_source_game_verified_on_instruction_level_cpu": True,
            "original_companion_rank_and_reward_verified": True,
            "native_companion_pet_verified_on_guest_z80": True,
            "native_pet_preserves_gameplay_verified": True,
            "native_pause_blocks_gameplay_and_mutes_psg_verified": True,
            "native_restart_restores_original_theme_verified": True,
            "actual_victory_palette_verified": True,
            "native_attract_demo_chord_started_from_victory": True,
            "native_attract_demo_full_solution_verified_on_guest_z80": True,
            "native_attract_demo_controller_free_actions_verified": 256,
            "native_attract_demo_semantic_trace_sha256": "f"*64,
            "native_attract_demo_screen_frames": 2350,
            "native_attract_demo_performed_first_original_move": True,
            "native_attract_demo_user_cancel_restored_game": True,
            "original_levels_replayed": 3,
            "controller_actions_replayed": 256,
            "hardware_screen_states_verified": 257,
            "semantic_controller_screen_trace_sha256": "f"*64,
            "semantic_trace_steps_hashed": 257,
            "total_instruction_budget_enforced": True,
            "total_frame_budget_enforced": True,
            "real_z80_instruction_count": 123456,
            "real_z80_active_joypad_port_reads": 2048,
            "real_z80_directions_seen_as_active_low_buttons": 15,
            "independent_cycle_exact_full_console_emulator_verified": False,
            "physical_hardware_verified": False,
            "rights_independently_verified": False,
            "distribution_licensed": False,
            "release_approved": False,
        }
        comparable = {
            "schema": "skeleton.game_builder.sega_reproducibility.v1",
            "target": target,
            "source_sha256": str(index)*64,
            "author_declaration_sha256": RIGHTS,
            "world_sha256": WORLD,
            "reference_replay_sha256": REPLAY,
            "toolchain_git_revision": TOOLCHAIN,
            "cartridge_sha256": str(index+3)*64,
            "cartridge_bytes": 32768,
            "checked_two_distinct_artifact_paths": True,
            "exact_rom_bytes_match": True,
            "source_and_authorship_digests_match": True,
            "two_compiler_executions_independently_verified": False,
            "source_rights_independently_verified": False,
            "gameplay_execution_verified": False,
            "real_console_hardware_verified": False,
            "developer_toolchain_authenticity_proven": False,
            "publication_licensed": False,
        }
        comparable["comparison_sha256"] = sha256(json.dumps(
            comparable, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        content["reproducibility"] = comparable
        paths = {
            "manifest": source / "manifest.json",
            "compile": root / (target + "-compilation-evidence.json"),
            "host": root / (target + "-host-gameplay-receipt.json"),
            "boot": root / (target + "-real-z80-boot.json"),
            "reproducibility": root / (target + "-reproducibility.json"),
            "native_route": root / (target + "-native-z80-gameplay.json"),
        }
        for name, path in paths.items():
            path.write_text(json.dumps(content[name], indent=2), encoding="utf-8")
        files[target] = paths
    return files


def _mutate(path: Path, field: str, value: object) -> None:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt[field] = value
    path.write_text(json.dumps(receipt), encoding="utf-8")


def test_two_real_console_formats_share_original_identity_not_binary(tmp_path):
    _fixtures(tmp_path)
    receipt = verify_ports(tmp_path)
    assert receipt["native_platforms_checked"] == [
        "sega_game_gear", "sega_master_system",
    ]
    assert receipt["gameplay_parity_verified"] is True
    assert receipt["independent_native_rom_formats_verified"] is True
    assert receipt["real_z80_startup_checked_per_platform"] is True
    assert receipt["original_on_cartridge_demo_equivalent_across_platforms"] is True
    assert receipt["native_attract_demo_entry_and_cancel_verified_on_both_platforms"] is True
    assert receipt["native_autonomous_full_game_replayed_on_both_platforms"] is True
    assert receipt["native_autonomous_guest_semantic_trace_sha256"] == "f"*64
    assert receipt["original_demo_controller_actions_verified_per_platform"] == 256
    assert receipt["original_demo_solution_sha256"] == "9"*64
    assert receipt["native_cartridge_rebuild_byte_equality_checked_per_platform"] is True
    assert set(receipt["native_rebuild_provenance_sha256_by_platform"]) == set(EXTS)
    assert all(len(value)==64 for value in receipt["native_rebuild_provenance_sha256_by_platform"].values())
    assert receipt["original_controller_actions_verified_per_platform"] == 256
    assert receipt["world_digest"] == WORLD
    assert receipt["full_native_z80_gameplay_replay_verified"] is True
    assert receipt["native_guest_semantic_trace_sha256"] == "f"*64
    assert receipt["native_guest_semantic_snapshots_verified_per_platform"] == 257
    assert receipt["native_z80_controller_actions_verified_per_platform"] == 256
    assert set(receipt["guest_z80_gameplay_receipt_sha256_by_platform"]) == set(EXTS)
    assert receipt["physical_hardware_verified"] is False
    assert receipt["release_approved"] is False
    assert len(receipt["receipt_sha256"]) == 64
    assert receipt == verify_ports(tmp_path)


@pytest.mark.parametrize("evidence,field,replacement", (
    ("manifest", "world_digest", "d" * 64),
    ("manifest", "reference_safe_replay_digest", "e" * 64),
    ("manifest", "source_rights_evidence_sha256", "f" * 64),
    ("manifest", "original_color_theme", "desert"),
    ("manifest", "original_demo_solution_sha256", "0"*64),
    ("manifest", "original_demo_playback_steps", 42),
    ("manifest", "original_demo_compressed_rom_bytes", 257),
    ("manifest", "original_demo_direction_encoding", "uncompressed"),
    ("manifest", "original_demo_autostart", True),
    ("manifest", "original_demo_external_content", True),
    ("manifest", "project_id", "unreviewed-work"),
    ("host", "original_controller_actions_verified", 257),
    ("host", "original_score_and_screen_state_verified", False),
    ("host", "original_native_solution_attract_mode_host_verified", False),
    ("host", "original_demo_controller_actions_verified", 0),
    ("host", "original_demo_screen_trace_sha256", "0"*64),
    ("native_route", "native_attract_demo_chord_started_from_victory", False),
    ("native_route", "native_attract_demo_full_solution_verified_on_guest_z80", False),
    ("native_route", "native_attract_demo_controller_free_actions_verified", 200),
    ("native_route", "native_attract_demo_semantic_trace_sha256", "0"*64),
    ("native_route", "native_attract_demo_screen_frames", 1),
    ("native_route", "native_attract_demo_performed_first_original_move", False),
    ("native_route", "native_attract_demo_user_cancel_restored_game", False),
    ("host", "full_console_emulator_playthrough_verified", True),
    ("boot", "hardware_boot_smoke_verified", False),
    ("boot", "physical_hardware_verified", True),
    ("compile", "real_rom_structure_verified", False),
    ("compile", "rom_sha256", "0" * 64),
    ("native_route", "semantic_controller_screen_trace_sha256", "0"*64),
    ("native_route", "semantic_trace_steps_hashed", 256),
    ("native_route", "total_instruction_budget_enforced", False),
    ("native_route", "total_frame_budget_enforced", "true"),
    ("native_route", "rom_sha256", "0" * 64),
    ("native_route", "original_world_digest", "d" * 64),
    ("native_route", "original_route_sha256", "e" * 64),
    ("native_route", "controller_actions_replayed", 100),
    ("native_route", "hardware_screen_states_verified", 256),
    ("native_route", "real_z80_instruction_count", 0),
    ("native_route", "real_z80_active_joypad_port_reads", 0),
    ("native_route", "real_z80_directions_seen_as_active_low_buttons", 0),
    ("native_route", "original_companion_rank_and_reward_verified", False),
    ("native_route", "native_companion_pet_verified_on_guest_z80", False),
    ("native_route", "native_pet_preserves_gameplay_verified", False),
    ("native_route", "native_pause_blocks_gameplay_and_mutes_psg_verified", False),
    ("native_route", "native_restart_restores_original_theme_verified", False),
    ("native_route", "actual_victory_palette_verified", False),
    ("native_route", "release_approved", True),
    ("reproducibility", "cartridge_sha256", "0" * 64),
    ("reproducibility", "toolchain_git_revision", "a" * 40),
    ("reproducibility", "source_sha256", "b" * 64),
    ("reproducibility", "world_sha256", "c" * 64),
    ("reproducibility", "author_declaration_sha256", "d" * 64),
    ("reproducibility", "source_rights_independently_verified", True),
    ("reproducibility", "checked_two_distinct_artifact_paths", False),
    ("reproducibility", "gameplay_execution_verified", True),
    ("reproducibility", "comparison_sha256", "e" * 64),
))
def test_cross_port_rights_and_machine_evidence_mismatches_fail_closed(
    tmp_path, evidence, field, replacement,
):
    files = _fixtures(tmp_path)
    _mutate(files["sega_game_gear"][evidence], field, replacement)
    with pytest.raises(Sega8PortParityError):
        verify_ports(tmp_path)


def test_cross_port_artifacts_cannot_hide_extra_receipts_or_symlink_sources(tmp_path):
    files = _fixtures(tmp_path)
    proof = files["sega_master_system"]["manifest"]
    duplicate = proof.parent / "shadow" / "manifest.json"
    duplicate.parent.mkdir()
    duplicate.write_bytes(proof.read_bytes())
    with pytest.raises(Sega8PortParityError, match="ambiguous"):
        verify_ports(tmp_path)
    duplicate.unlink()
    linked = files["sega_game_gear"]["boot"]
    original_bytes = linked.read_bytes()
    linked.unlink()
    external = tmp_path / "outside.json"
    external.write_bytes(original_bytes)
    linked.symlink_to(external)
    with pytest.raises(Sega8PortParityError):
        verify_ports(tmp_path)


def test_cross_port_rejects_artifact_hardlinks(tmp_path):
    if not hasattr(os, "link"):
        pytest.skip("POSIX hardlinks needed")
    files = _fixtures(tmp_path)
    ref = files["sega_master_system"]["compile"]
    extra = tmp_path / "outside-duplicate"
    os.link(ref, extra)
    with pytest.raises(Sega8PortParityError):
        verify_ports(tmp_path)



def test_cross_port_refuses_missing_rebuild_receipt_even_after_compiled_rom_boot(tmp_path):
    files=_fixtures(tmp_path)
    files["sega_game_gear"]["reproducibility"].unlink()
    with pytest.raises(Sega8PortParityError,match="missing/ambiguous"):
        verify_ports(tmp_path)


@pytest.mark.parametrize("value",[None,0,"false",True,1,[],{"forged":"game"}])
def test_cross_port_refuses_fake_executable_provenance_status(tmp_path,value):
    files=_fixtures(tmp_path)
    _mutate(files["sega_master_system"]["reproducibility"],
            "two_compiler_executions_independently_verified",value)
    with pytest.raises(Sega8PortParityError):
        verify_ports(tmp_path)


def test_cross_port_refuses_duplicate_json_properties_in_game_reproducibility(tmp_path):
    files=_fixtures(tmp_path)
    path=files["sega_game_gear"]["reproducibility"]
    data=path.read_bytes()
    # Duplicate schema values are ambiguous across JSON parsers.
    path.write_bytes(data.replace(b'{',b'{"schema":"fake",',1))
    with pytest.raises(Sega8PortParityError):
        verify_ports(tmp_path)


def test_cross_port_refuses_unreviewed_property_with_recalculated_digest(tmp_path):
    files=_fixtures(tmp_path)
    path=files["sega_master_system"]["reproducibility"]
    data=json.loads(path.read_text(encoding="utf-8"))
    data["commercial_game_shipped"]=True
    data.pop("comparison_sha256")
    data["comparison_sha256"]=sha256(json.dumps(
        data,sort_keys=True,separators=(",", ":"),ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    path.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(Sega8PortParityError,match="unreviewed"):
        verify_ports(tmp_path)


def test_cross_port_refuses_checksum_correct_but_rebuilt_ROM_digest_replacement(tmp_path):
    files=_fixtures(tmp_path)
    path=files["sega_game_gear"]["reproducibility"]
    data=json.loads(path.read_text(encoding="utf-8"))
    data["cartridge_sha256"]="0"*64
    data.pop("comparison_sha256")
    data["comparison_sha256"]=sha256(json.dumps(
        data,sort_keys=True,separators=(",", ":"),ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    path.write_text(json.dumps(data),encoding="utf-8")
    with pytest.raises(Sega8PortParityError,match="cartridge_sha256"):
        verify_ports(tmp_path)



def test_cross_port_output_refuses_linked_or_existing_receipt(tmp_path):
    from scripts.game_builder.sega_reproducibility_ci import emit_receipt
    _fixtures(tmp_path)
    result=verify_ports(tmp_path)
    destination=tmp_path/"original-port-proof.json"
    emit_receipt(destination,result)
    initial=destination.read_bytes()
    with pytest.raises(FileExistsError):
        emit_receipt(destination,{"release_approved":True})
    assert destination.read_bytes()==initial
    external=tmp_path/"target.json"
    external.write_text('{"original":true}',encoding="utf-8")
    alias=tmp_path/"alias.json"
    alias.symlink_to(external)
    with pytest.raises(OSError):
        emit_receipt(alias,result)
    assert json.loads(external.read_text())=={"original":True}


def test_cross_port_output_parent_symlink_cannot_redirect_a_game_receipt(tmp_path):
    from scripts.game_builder.sega_reproducibility_ci import emit_receipt
    _fixtures(tmp_path)
    result=verify_ports(tmp_path)
    actual=tmp_path/"actual-root"
    actual.mkdir()
    alias=tmp_path/"linked-output"
    alias.symlink_to(actual,target_is_directory=True)
    with pytest.raises(ValueError):
        emit_receipt(alias/"evidence.json",result)
    assert list(actual.iterdir())==[]



def test_cross_console_rejects_divergent_guest_cpu_semantic_gameplay_trace(tmp_path):
    paths=_fixtures(tmp_path)
    _mutate(paths["sega_game_gear"]["native_route"],
            "semantic_controller_screen_trace_sha256","e"*64)
    with pytest.raises(Sega8PortParityError,match="semantic trace"):
        verify_ports(tmp_path)


@pytest.mark.parametrize("value",[True,False,None,"true",0,1,[],{}])
def test_native_guest_replay_budget_attestation_cannot_be_suppressed(tmp_path,value):
    files=_fixtures(tmp_path)
    _mutate(files["sega_master_system"]["native_route"],
            "total_instruction_budget_enforced",value)
    if value is True:
        assert verify_ports(tmp_path)["native_guest_semantic_snapshots_verified_per_platform"]==257
    else:
        with pytest.raises(Sega8PortParityError):
            verify_ports(tmp_path)
