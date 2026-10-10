"""Real end-to-end local Linux C99 puzzle build and replay tests.

No emulator claims and no system compiler execution in the HTTP application.
The native game uses original seeded puzzles and independently solved grids.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import json
import shutil
import subprocess
import sys

import pytest

from skeleton.ai.webcrawler.dragon_native_desktop import (
    COMPILER_FLAGS, _elf_format, _selftest_stages, build_native_puzzle_executable,
    publish_native_puzzle_executable, verify_native_puzzle_executable,
)
from skeleton.ai.webcrawler.dragon_native_production import (
    PortableGameDesign, ProductionRequest,
)

def spec(**changes):
    base = ProductionRequest(
        title="Original Starlight Puzzle",
        style="fixed_screen_puzzle",
        targets=("pc_linux",),
        seed=754,
        original_work_attested=True,
        portable_design=PortableGameDesign(
            palette="vga_dusk", hero="explorer", quest_theme="clockwork",
            difficulty=6, stages=4, candidates=5,
        ),
    )
    return replace(base, **changes)

def repackage(data: bytes, edited: dict[str, bytes]) -> bytes:
    result = BytesIO()
    with ZipFile(BytesIO(data)) as read, ZipFile(result, "w", ZIP_DEFLATED) as write:
        for name in read.namelist():
            write.writestr(name, edited.get(name, read.read(name)))
    return result.getvalue()


@pytest.mark.parametrize("kwargs", [
    {"authorized": False},
])
def test_local_executable_build_requires_explicit_operator_authority(kwargs):
    with pytest.raises(PermissionError):
        build_native_puzzle_executable(spec(), **kwargs)


@pytest.mark.parametrize("changes", [
    {"targets": ("game_boy",)},
    {"targets": ("pc_windows",)},
    {"targets": ("pc_linux", "pc_macos")},
    {"style": "arcade_score_attack"},
    {"compile_roms": True},
    {"require_compiled": True},
])
def test_native_desktop_lane_does_not_pretend_cross_compilation(changes):
    if sys.platform != "linux":
        pytest.skip("native executable compilation is Linux only")
    with pytest.raises(ValueError):
        build_native_puzzle_executable(spec(**changes), authorized=True)


@pytest.mark.parametrize("value", [
    b"", b"not an executable",
    b"\x7fELF\xff\x01" + b"\0" * 58,
    b"\x7fELF\x02\x01" + b"\0" * 58,
])
def test_native_executable_verifier_rejects_non_elf_or_wrong_kind(value):
    with pytest.raises(ValueError):
        _elf_format(value)


@pytest.mark.parametrize("lines,stage_count", [
    ("DRAGON_NATIVE_PUZZLE_SELFTEST PASS stages=2", 2),
    ("PUZZLE_STAGE_PASS level=1 moves=10 pushes=1\n"
     "PUZZLE_STAGE_PASS level=1 moves=12 pushes=1\n"
     "DRAGON_NATIVE_PUZZLE_SELFTEST PASS stages=2", 2),
    ("PUZZLE_STAGE_PASS level=1 moves=10 pushes=1\n"
     "DRAGON_NATIVE_PUZZLE_SELFTEST PASS stages=2", 2),
    ("PUZZLE_STAGE_PASS level=1 moves=10 pushes=1\n"
     "PUZZLE_STAGE_PASS level=2 moves=12 pushes=1\n"
     "DRAGON_NATIVE_PUZZLE_SELFTEST PASS stages=2\n"
     "PUZZLE_STAGE_PASS level=3 moves=2 pushes=0", 2),
])
def test_exact_compiled_gameplay_runtime_evidence_cannot_be_faked(lines, stage_count):
    with pytest.raises(ValueError):
        _selftest_stages(lines, stage_count)


@pytest.mark.skipif(sys.platform != "linux" or not shutil.which("cc"),
                    reason="requires trusted local Linux C compiler")
@pytest.mark.parametrize("stages,difficulty", [(1, 2), (4, 6), (8, 10)])
def test_real_native_puzzle_executable_compiles_and_replays_every_level(stages, difficulty):
    game = spec(portable_design=PortableGameDesign(
        stages=stages, difficulty=difficulty, candidates=4,
        hero="robot", quest_theme="space",
    ))
    data, evidence = build_native_puzzle_executable(game, authorized=True)
    result = verify_native_puzzle_executable(data)
    assert result["status"] == "source_and_native_executable_structurally_verified"
    assert result["source_level_proofs"] == stages
    assert evidence["runtime_selftest"] == "native_executable_all_stages_passed"
    assert evidence["runtime_stages_verified"] == stages
    assert evidence["compiler_flags"] == COMPILER_FLAGS
    assert result["executable_sha256"] == evidence["executable_sha256"]
    with ZipFile(BytesIO(data)) as archive:
        binary = archive.read("binary/dragon_game")
        assert binary[:4] == b"\x7fELF"
        assert len(binary) == evidence["executable_bytes"]
        assert sha256(binary).hexdigest() == evidence["executable_sha256"]
        assert archive.read("source/native-source-release.zip")[:2] == b"PK"


@pytest.mark.skipif(sys.platform != "linux" or not shutil.which("cc"),
                    reason="requires local Linux C compiler")
def test_real_native_puzzle_release_content_addressed_and_replay_safe(tmp_path):
    game = spec()
    first = publish_native_puzzle_executable(game, tmp_path, authorized=True)
    assert first["status"] == "native_linux_executable_built_and_selftested"
    path = tmp_path / first["filename"]
    assert path.read_bytes()
    assert first["filename"] == "dragon-native-puzzle-" + first["archive_sha256"][:20] + ".zip"
    assert verify_native_puzzle_executable(path.read_bytes())[
        "runtime_stages_claimed_by_builder"] == 4
    # Executable bytes can differ across compilers; a second build must never
    # replace the first immutable release under a conflicting content identity.
    second = publish_native_puzzle_executable(game, tmp_path, authorized=True)
    assert (tmp_path / second["filename"]).is_file()


@pytest.mark.skipif(sys.platform != "linux" or not shutil.which("cc"),
                    reason="requires local Linux C compiler")
def test_native_puzzle_packaging_detects_altered_binary_and_fake_runtime(tmp_path):
    data, evidence = build_native_puzzle_executable(spec(), authorized=True)
    with ZipFile(BytesIO(data)) as z:
        manifest = json.loads(z.read("native-executable-evidence.json"))
        binary = z.read("binary/dragon_game")
    altered = repackage(data, {"binary/dragon_game": binary + b"\0"})
    with pytest.raises(ValueError, match="mismatch"):
        verify_native_puzzle_executable(altered)
    manifest["runtime_stages_verified"] = 500
    forged = repackage(data, {
        "native-executable-evidence.json": json.dumps(manifest).encode(),
    })
    with pytest.raises(ValueError, match="mismatch"):
        verify_native_puzzle_executable(forged)
