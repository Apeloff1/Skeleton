"""Cross-port identity, gameplay equality and rights-bound Sega release tests.

Fixtures are synthetic JSON receipts only; they neither forge compiled ROM
execution nor include firmware, game ROMs, or outside expressive material.
"""
from __future__ import annotations

from copy import deepcopy
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
        paths = {
            "manifest": source / "manifest.json",
            "compile": root / (target + "-compilation-evidence.json"),
            "host": root / (target + "-host-gameplay-receipt.json"),
            "boot": root / (target + "-real-z80-boot.json"),
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
