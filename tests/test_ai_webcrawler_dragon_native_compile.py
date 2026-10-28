"""Offline compiler adapter and claim-boundary checks for native ROMs."""
from __future__ import annotations
from hashlib import sha256
import shutil
import pytest
from skeleton.ai.webcrawler.dragon_native_projects import render_native_project
from skeleton.ai.webcrawler.dragon_native_compile import (
    _verify, compile_local,
)
from skeleton.ai.webcrawler.dragon_native_cli import emit_demo
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic

def project(target):
    return render_native_project(
        title="Dragon Tiny Adventure",target_id=target,style="arcade_score_attack",
        candidate_id=sha256(("Dragon Tiny Adventure\0"+target+"\0arcade_score_attack").encode()).hexdigest(),
        mechanics=(Mechanic.MOVEMENT,Mechanic.EXPLORATION),authorized=True)

def test_missing_toolchain_never_claims_rom_is_built(tmp_path,monkeypatch):
    destination=tmp_path/"native"
    emit_demo("game_boy",destination)
    monkeypatch.setattr(shutil,"which",lambda name:None)
    outcome=compile_local(project("game_boy"),destination,authorized=True)
    assert outcome.state=="toolchain_missing"
    assert outcome.binary_path=="" and outcome.binary_sha256==""
    assert outcome.bytes_written==0

def test_modified_code_or_unauthorized_compilation_rejected(tmp_path):
    destination=tmp_path/"native"
    emit_demo("game_boy",destination)
    p=project("game_boy")
    with pytest.raises(PermissionError):
        compile_local(p,destination,authorized=False)
    (destination/"src/main.asm").write_text("untrusted script")
    with pytest.raises(ValueError,match="changed"):
        compile_local(p,destination,authorized=True)

def test_invalid_roms_are_not_promoted():
    assert not _verify("nes",b"")
    assert not _verify("nes",b"MZ")
    assert not _verify("game_boy",b"\0"*32768)
    valid=bytearray(16+32768+8192)
    valid[:6]=b"NES\x1a\x02\x01"
    assert _verify("nes",bytes(valid))
    assert not _verify("nes",bytes(valid[:-1]))

def test_real_gb_rom_if_rgbds_toolchain_installed(tmp_path):
    if not all(shutil.which(x) for x in ("rgbasm","rgblink","rgbfix")):
        pytest.skip("RGBDS unavailable; this does not count as validated ROM execution")
    destination=tmp_path/"gb"
    emit_demo("game_boy",destination)
    result=compile_local(project("game_boy"),destination,authorized=True)
    assert result.state=="compiled_native",result.message
    assert result.binary_path.endswith(".gb")
    assert result.bytes_written>=32768
    assert result.binary_sha256==sha256((destination/"build/dragon.gb").read_bytes()).hexdigest()

def test_real_nes_rom_if_cc65_toolchain_installed(tmp_path):
    if not all(shutil.which(x) for x in ("ca65","ld65")):
        pytest.skip("cc65 unavailable; this does not count as validated NES ROM")
    destination=tmp_path/"nes"
    emit_demo("nes",destination)
    result=compile_local(project("nes"),destination,authorized=True)
    assert result.state=="compiled_native",result.message
    assert result.binary_path.endswith(".nes")
    assert _verify("nes",(destination/"build/dragon.nes").read_bytes())


def test_real_c64_compilation_through_public_adapter(tmp_path):
    if not shutil.which("cl65"):
        pytest.skip("cc65 unavailable; C64 CLI compilation is not validated")
    destination = tmp_path / "c64"
    emit_demo("commodore_64", destination)
    result = compile_local(project("commodore_64"), destination, authorized=True)
    assert result.state == "compiled_native", result.message
    binary = (destination / "build/dragon.prg").read_bytes()
    assert _verify("commodore_64", binary)
    assert result.binary_sha256 == sha256(binary).hexdigest()
    assert not list(destination.glob(".dragon-build-*"))
    # The cc65 BASIC SYS entry must address actual machine code, not a header.
    for corrupted in (b"", b"\x01\x08" + b"\0" * 100, binary[:14],
                      b"\x00\x08" + binary[2:], binary[:6] + b"X" + binary[7:]):
        assert not _verify("commodore_64", corrupted)
    # Rebuilding the same source produces the same content identity.
    repeated = compile_local(project("commodore_64"), destination, authorized=True)
    assert repeated.binary_sha256 == result.binary_sha256


def _fake_tools(monkeypatch, function):
    from skeleton.ai.webcrawler import dragon_native_compile as compiler
    import sys
    monkeypatch.setattr(compiler.shutil, "which", lambda name: sys.executable)
    monkeypatch.setattr(compiler, "_run_bounded", function)


def test_stale_output_cannot_be_accepted_from_a_noop_compiler(tmp_path, monkeypatch):
    destination = tmp_path / "nes"
    emit_demo("nes", destination)
    (destination / "build").mkdir()
    stale = destination / "build/dragon.nes"
    original = b"NES\x1a\x02\x01" + bytes(16 + 32768 + 8192 - 6)
    stale.write_bytes(original)
    _fake_tools(monkeypatch, lambda *args, **kwargs: (0, ""))
    result = compile_local(project("nes"), destination, authorized=True)
    assert result.state == "missing_binary"
    assert result.binary_sha256 == ""
    assert stale.read_bytes() == original
    assert not list(destination.glob(".dragon-build-*"))


@pytest.mark.parametrize("kind", ["root", "source_directory", "build_directory", "output"])
def test_links_are_rejected_before_any_compiler_execution(tmp_path, monkeypatch, kind):
    destination = tmp_path / "nes"
    emit_demo("nes", destination)
    outside = tmp_path / "outside"
    outside.mkdir()
    if kind == "root":
        linked = tmp_path / "linked"
        linked.symlink_to(destination, target_is_directory=True)
        destination = linked
    elif kind == "source_directory":
        (destination / "src").rename(outside / "src")
        (destination / "src").symlink_to(outside / "src", target_is_directory=True)
    elif kind == "build_directory":
        (destination / "build").symlink_to(outside, target_is_directory=True)
    else:
        (destination / "build").mkdir()
        (destination / "build/dragon.nes").symlink_to(outside / "missing.nes")
    def forbidden(*args, **kwargs):
        pytest.fail("compiler must not run for linked paths")
    _fake_tools(monkeypatch, forbidden)
    with pytest.raises(ValueError, match="symlink"):
        compile_local(project("nes"), destination, authorized=True)
    assert not (outside / "missing.nes").exists()


@pytest.mark.parametrize("state", ["failure", "timeout", "invalid", "oversized", "launch_failure"])
def test_failed_build_preserves_previous_artifact_and_cleans_work(tmp_path, monkeypatch, state):
    import subprocess
    destination = tmp_path / "nes"
    emit_demo("nes", destination)
    (destination / "build").mkdir()
    previous = destination / "build/dragon.nes"
    previous.write_bytes(b"previous build")
    def execute(argv, *, cwd, **kwargs):
        if state == "timeout":
            raise subprocess.TimeoutExpired(argv, 5)
        if state == "launch_failure":
            raise OSError("tool removed")
        (cwd / "build/dragon.nes").write_bytes(b"x" * (2_000_001 if state == "oversized" else 10))
        return (1, "failed") if state == "failure" else (0, "")
    _fake_tools(monkeypatch, execute)
    result = compile_local(project("nes"), destination, authorized=True)
    assert result.state == {"failure": "compile_failed", "timeout": "timed_out",
                            "invalid": "invalid_binary", "oversized": "invalid_binary",
                            "launch_failure": "compile_failed"}[state]
    assert result.binary_path == "" and result.binary_sha256 == ""
    assert previous.read_bytes() == b"previous build"
    assert not list(destination.glob(".dragon-build-*"))


def test_changed_project_mapping_is_not_a_valid_snapshot(tmp_path):
    destination = tmp_path / "nes"
    emit_demo("nes", destination)
    p = project("nes")
    p.files["src/main.s"] += "\n; changed"
    (destination / "src/main.s").write_text(p.files["src/main.s"])
    with pytest.raises(ValueError, match="digest"):
        compile_local(p, destination, authorized=True)


@pytest.mark.parametrize("unsafe", ["../outside", "/absolute", "src/../outside", "src\\outside", "C:/outside"])
def test_project_path_validation_precedes_io(tmp_path, unsafe):
    from dataclasses import replace
    from skeleton.ai.webcrawler.dragon_native_projects import digest
    p = project("nes")
    files = {unsafe: "bad"}
    p = replace(p, files=files, digest=digest(files))
    with pytest.raises(ValueError, match="unsafe"):
        compile_local(p, tmp_path, authorized=True)


def test_actual_subprocess_diagnostics_are_bounded(tmp_path):
    import os
    import sys
    from skeleton.ai.webcrawler.dragon_native_compile import _run_bounded, MAX_BUILD_LOG_BYTES
    code, output = _run_bounded(
        (sys.executable, "-c", "import os; os.write(1, b'x' * 200000)"),
        cwd=tmp_path, env=dict(os.environ), timeout=5)
    assert code != 0 and "exceeded budget" in output
    assert len(output) < MAX_BUILD_LOG_BYTES


def test_actual_subprocess_timeout_is_reported(tmp_path):
    import os
    import sys
    import subprocess
    from skeleton.ai.webcrawler.dragon_native_compile import _run_bounded
    with pytest.raises(subprocess.TimeoutExpired):
        _run_bounded((sys.executable, "-c", "import time; time.sleep(5)"),
                     cwd=tmp_path, env=dict(os.environ), timeout=0.05)


def test_cli_rejects_linked_root_and_preflights_before_overwrite(tmp_path):
    destination = tmp_path / "nes"
    emit_demo("nes", destination)
    linked = tmp_path / "linked"
    linked.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        emit_demo("nes", linked, overwrite=True)
    # A later unsafe source must be found before the earlier Makefile changes.
    (destination / "Makefile").write_text("preserve this")
    source = destination / "src/main.s"
    source.unlink()
    source.symlink_to(tmp_path / "outside.s")
    with pytest.raises(ValueError, match="symlink"):
        emit_demo("nes", destination, overwrite=True)
    assert (destination / "Makefile").read_text() == "preserve this"
    assert not (tmp_path / "outside.s").exists()


def test_cli_overwrite_does_not_mutate_hardlinked_user_file(tmp_path):
    import os
    destination = tmp_path / "nes"
    emit_demo("nes", destination)
    outside = tmp_path / "user.txt"
    outside.write_text("user content")
    (destination / "Makefile").unlink()
    os.link(outside, destination / "Makefile")
    emit_demo("nes", destination, overwrite=True)
    assert outside.read_text() == "user content"
    assert (destination / "Makefile").read_text() != "user content"


def test_nes_rejects_unsupported_mapper_trainer_and_header_fields():
    valid = bytearray(b"NES\x1a\x02\x01" + bytes(16 + 32768 + 8192 - 6))
    for offset, value in ((6, 0x10), (6, 4), (7, 8), (8, 1), (15, 1)):
        changed = valid.copy()
        changed[offset] = value
        assert not _verify("nes", bytes(changed))


def test_real_gb_corruption_and_misdeclared_size_are_rejected(tmp_path):
    if not all(shutil.which(x) for x in ("rgbasm", "rgblink", "rgbfix")):
        pytest.skip("RGBDS unavailable")
    emit_demo("game_boy", tmp_path / "gb")
    result = compile_local(project("game_boy"), tmp_path / "gb", authorized=True)
    assert result.state == "compiled_native", result.message
    blob = bytearray((tmp_path / "gb/build/dragon.gb").read_bytes())
    blob[-1] ^= 1
    assert not _verify("game_boy", bytes(blob))
    blob[-1] ^= 1
    blob[0x148] = 1
    # Even an internally checksummed ROM is invalid if size differs from header.
    blob[0x14D] = (-sum(blob[0x134:0x14D]) - 25) & 255
    total = (sum(blob[:0x14E]) + sum(blob[0x150:])) & 65535
    blob[0x14E:0x150] = total.to_bytes(2, "big")
    assert not _verify("game_boy", bytes(blob))


def test_source_snapshot_cannot_include_pretend_build_output(tmp_path):
    from dataclasses import replace
    from skeleton.ai.webcrawler.dragon_native_projects import digest
    p = project("nes")
    files = {"build/dragon.nes": "fake prior build"}
    p = replace(p, files=files, digest=digest(files))
    with pytest.raises(ValueError, match="build artifacts"):
        compile_local(p, tmp_path, authorized=True)
