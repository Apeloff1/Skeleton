"""Use the public native-game CLI without trusting platform names or fake ROMs."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.native_game_cli import build_game


def test_native_game_rejects_symlink_rights_source_before_any_binary_or_directory(tmp_path):
    from skeleton.ai.game_builder.native_game_cli import build_game

    original = tmp_path / "evidence.txt"
    original.write_bytes(b"New authored original play mechanics.")
    alias = tmp_path / "evidence-alias.txt"
    try:
        alias.symlink_to(original)
    except OSError:
        pytest.skip("symlink unavailable")
    result_folder = tmp_path / "never-created"
    with pytest.raises(ValueError, match="bounded local regular file"):
        build_game(
            target="windows_modern", basis="bandai_wonderswan",
            project_id="owned-homebrew", title="Own Game", seed=19,
            width=17, height=15, levels=3,
            collectibles=3, hazards=4, health=4,
            rights_evidence=alias, creative_identity=("own art", "own gameplay"),
            output=result_folder, authorized=True,
        )
    assert not result_folder.exists()


@pytest.mark.parametrize("target,files", [
    ("commodore_64", {"game.c", "Makefile", "manifest.json"}),
    ("apple_ii", {"game.c", "Makefile", "manifest.json"}),
    ("sinclair_zx_spectrum", {"game.asm", "Makefile", "README.txt", "manifest.json", "make_tap.py"}),
    ("msx1", {"game.asm", "Makefile", "README.txt", "manifest.json", "make_rom.py"}),
    ("colecovision", {"game.asm", "Makefile", "manifest.json", "make_col.py"}),
    ("vectrex", {"game.asm", "Makefile", "manifest.json"}),
    ("sega_master_system", {"game.asm", "Makefile", "README.txt", "manifest.json", "make_sms.py"}),
    ("sega_game_gear", {"game.c", "Makefile", "manifest.json"}),
    ("atari_400_800", {"game.c", "Makefile", "manifest.json"}),
    ("dos_vga", {"game.asm", "Makefile", "manifest.json"}),
    ("nintendo_game_boy", {"main.asm", "Makefile", "manifest.json"}),
    ("nintendo_game_boy_color", {"main.asm", "Makefile", "manifest.json"}),
    ("nintendo_famicom", {"main.s", "nes.cfg", "Makefile", "manifest.json"}),
    ("windows_modern", {"game.c", "CMakeLists.txt", "manifest.json"}),
    ("linux_desktop", {"game.c", "CMakeLists.txt", "manifest.json"}),
    ("macos_modern", {"game.c", "CMakeLists.txt", "manifest.json"}),
])
def test_native_game_cli_produces_real_source_for_target_without_shell(tmp_path, target, files):
    receipt = tmp_path / "my-original-authorship.txt"
    receipt.write_text("Original game authored by the current user. No inherited ROMs.", encoding="utf-8")
    output = tmp_path / target
    result = build_game(
        target=target, basis="bandai_wonderswan",
        project_id="fully-original", title="Original Adventure",
        seed=10482, width=17, height=15, levels=2,
        collectibles=2, hazards=3, health=4,
        rights_evidence=receipt,
        creative_identity=("original-maze", "original-palette"),
        output=output, authorized=True,
    )
    assert result["target"] == target
    assert result["source_basis"] == "bandai_wonderswan"
    assert result["native_binary_built"] is False
    assert result["compiler_execution"] is False
    assert result["rights_independently_verified"] is False
    assert len(result["winning_replay_digest"]) == 64
    assert result["source_kind"].startswith("native_")
    # Every exported source now includes an integrity attestation. Verify its
    # binding rather than silently excluding it from the expected file set.
    assert {p.name for p in output.iterdir()} == files | {"source_attestation.json"}
    attestation = json.loads((output / "source_attestation.json").read_text())
    assert attestation["schema"] == "skeleton.game_builder.source_attestation.v1"
    assert attestation["target"] == target
    assert attestation["project_id"] == "fully-original"
    assert attestation["world_digest"] == result["world_digest"]
    assert attestation["reference_replay_digest"] == result["winning_replay_digest"]
    assert attestation["source_content_digest"] == result["source_content_digest"]
    assert attestation["rights_independently_verified"] is False
    assert attestation["binary_compiled"] is False
    for name, digest in attestation["input_files"].items():
        assert name in files
        assert sha256((output / name).read_bytes()).hexdigest() == digest
    assert attestation["attestation_digest"] == canonical_digest(
        {key: value for key, value in attestation.items() if key != "attestation_digest"}
    )
    assert json.loads((output / "manifest.json").read_text())["world_digest"] == result["world_digest"]
    with pytest.raises(FileExistsError):
        build_game(
            target=target, basis="bandai_wonderswan",
            project_id="fully-original", title="Original Adventure",
            seed=10482, width=17, height=15, levels=2,
            collectibles=2, hazards=3, health=4,
            rights_evidence=receipt,
            creative_identity=("original-maze", "original-palette"),
            output=output, authorized=True,
        )


def test_native_game_cli_refuses_no_authorization_missing_evidence_and_unknown_platform(tmp_path):
    evidence = tmp_path / "authorship.txt"
    evidence.write_text("I created the original tiles and gameplay.", encoding="utf-8")
    settings = dict(
        target="nintendo_game_boy", basis="bandai_wonderswan",
        project_id="fully-original", title="Original Adventure",
        seed=14, width=11, height=11, levels=1,
        collectibles=1, hazards=1, health=3,
        rights_evidence=evidence,
        creative_identity=("original-maze",),
        output=tmp_path / "game",
    )
    with pytest.raises(PermissionError):
        build_game(**settings, authorized=False)
    assert not settings["output"].exists()
    with pytest.raises(ValueError, match="no real native"):
        build_game(**(settings | {"target": "sony_ps5"}), authorized=True)
    with pytest.raises(ValueError, match="unregistered"):
        build_game(**(settings | {"basis": "made_up_console"}), authorized=True)
    with pytest.raises(ValueError, match="ordinary local"):
        build_game(**(settings | {"rights_evidence": tmp_path / "missing"}), authorized=True)
    assert not settings["output"].exists()
