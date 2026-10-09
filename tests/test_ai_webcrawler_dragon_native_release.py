"""Real compiled native release receipts, binary magic, and replay evidence."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json,platform,shutil
import pytest
from skeleton.ai.webcrawler.dragon_native_release import (
    host_target,format_for_bytes,build_native_release,
)

def test_host_release_targets_are_machine_native_only():
    assert host_target("Linux")=="pc_linux"
    assert host_target("Windows")=="pc_windows"
    assert host_target("Darwin")=="pc_macos"
    with pytest.raises(ValueError):
        host_target("game_boy")

def test_native_executable_magic_checks_elf_pe_macho_not_extensions():
    elf=b"\x7fELF"+bytes(160)
    assert format_for_bytes(elf,"linux")=="elf"
    macho=bytes.fromhex("cffaedfe")+bytes(160)
    assert format_for_bytes(macho,"darwin")=="mach_o"
    win=bytearray(180)
    win[:2]=b"MZ"
    win[60:64]=(128).to_bytes(4,"little")
    win[128:132]=b"PE\x00\x00"
    assert format_for_bytes(bytes(win),"windows")=="portable_executable"
    for malformed,host in (
        (b"garbage"*20,"linux"),
        (b"MZ"+bytes(200),"windows"),
        (elf,"windows"),
        (macho,"linux"),
        (b"MZ","windows"),
    ):
        with pytest.raises(ValueError):
            format_for_bytes(malformed,host)

def test_packaged_binary_is_real_local_executable_and_attached_to_its_source(tmp_path):
    if not shutil.which("cmake") or not (shutil.which("cc") or shutil.which("cl")):
        pytest.skip("CMake and native host C compiler unavailable")
    if platform.system().lower() not in ("linux","windows","darwin"):
        pytest.skip("native binary packaging not implemented for host OS")
    out=tmp_path/"native_game"
    verified=build_native_release(out)
    assert verified.schema=="skeleton.ai.dragon.native_binary_release.v1"
    assert verified.selftest_state=="native_selftest_passed"
    assert verified.selftest_stage_lines==4
    assert verified.source_file_count>=5
    assert verified.binary_sha256 and len(verified.binary_sha256)==64
    assert verified.artifact_zip_sha256 and len(verified.artifact_zip_sha256)==64
    assert verified.target==host_target()
    manifest=json.loads((out/"dragon-native-release.json").read_text())
    assert manifest["binary_sha256"]==verified.binary_sha256
    assert "no player certification" in verified.claim_boundary
    packaged=out/"dragon-native-release.zip"
    assert sha256(packaged.read_bytes()).hexdigest()==verified.artifact_zip_sha256
    with ZipFile(packaged) as z:
        names=set(z.namelist())
        binary_name="dragon_game.exe" if platform.system().lower()=="windows" else "dragon_game"
        assert names=={binary_name,"native-release.json","README.txt"}
        binary=z.read(binary_name)
        assert sha256(binary).hexdigest()==verified.binary_sha256
        assert format_for_bytes(binary,platform.system().lower())==verified.binary_format
        receipt=json.loads(z.read("native-release.json"))
        assert receipt["source_fingerprint"]==verified.source_fingerprint
        assert receipt["binary_size"]==len(binary)
        assert receipt["selftest_stage_lines"]==4
    with pytest.raises(ValueError,match="empty"):
        build_native_release(out)


def test_sparse_isolated_native_release_has_no_monorepo_imports(tmp_path):
    """The real build must work with only two source files, as on Windows CI."""
    import subprocess,sys
    from skeleton.ai.webcrawler import dragon_native_puzzle,dragon_native_release
    isolated=tmp_path/"minimal-release"
    isolated.mkdir()
    shutil.copyfile(dragon_native_puzzle.__file__,
                    isolated/"dragon_native_puzzle.py")
    shutil.copyfile(dragon_native_release.__file__,
                    isolated/"dragon_native_release.py")
    cli=subprocess.run(
        [sys.executable,str(isolated/"dragon_native_release.py"),"--help"],
        cwd=isolated,capture_output=True,text=True,timeout=10)
    assert cli.returncode==0,(cli.stdout,cli.stderr)
    assert "--out" in cli.stdout
    if not shutil.which("cmake") or not (shutil.which("cc") or shutil.which("cl")):
        pytest.skip("host C compiler or CMake missing")
    release=subprocess.run(
        [sys.executable,str(isolated/"dragon_native_release.py"),
         "--out",str(tmp_path/"isolated-build")],
        cwd=isolated,capture_output=True,text=True,timeout=180)
    assert release.returncode==0,(release.stdout,release.stderr)
    assert "DRAGON_NATIVE_RELEASE_PASS" in release.stdout
    receipt=json.loads((tmp_path/"isolated-build"/"dragon-native-release.json").read_text())
    assert receipt["selftest_state"]=="native_selftest_passed"
    assert receipt["source_file_count"]==6
    assert receipt["selftest_stage_lines"]==4
