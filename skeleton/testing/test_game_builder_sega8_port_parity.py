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
    assert receipt["native_cartridge_rebuild_byte_equality_checked_per_platform"] is True
    assert receipt["original_controller_actions_verified_per_platform"] == 256
    assert receipt["world_digest"] == WORLD
    assert receipt["full_native_z80_gameplay_replay_verified"] is False
    assert receipt["physical_hardware_verified"] is False
    assert receipt["release_approved"] is False
    assert len(receipt["receipt_sha256"]) == 64
    assert receipt == verify_ports(tmp_path)


@pytest.mark.parametrize("evidence,field,replacement", (
    ("manifest", "world_digest", "d" * 64),
    ("manifest", "reference_safe_replay_digest", "e" * 64),
    ("manifest", "source_rights_evidence_sha256", "f" * 64),
    ("manifest", "original_color_theme", "desert"),
    ("manifest", "project_id", "unreviewed-work"),
    ("host", "original_controller_actions_verified", 257),
    ("host", "original_score_and_screen_state_verified", False),
    ("host", "full_console_emulator_playthrough_verified", True),
    ("boot", "hardware_boot_smoke_verified", False),
    ("boot", "physical_hardware_verified", True),
    ("compile", "real_rom_structure_verified", False),
    ("compile", "rom_sha256", "0" * 64),
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
    path.write_bytes(data.replace(b'{"schema":',b'{"schema":"fake", "schema":',1))
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
