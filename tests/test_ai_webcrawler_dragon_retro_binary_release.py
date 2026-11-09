"""Native binary bytes from 3 historical gaming architectures, not fake labels."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json,shutil
import pytest

from skeleton.ai.webcrawler.dragon_retro_binary_release import (
    TARGETS,COMPILERS,OUTPUTS,identify_binary,build_original_hardware,
    _member,
)

def test_release_targets_bind_three_different_compilers():
    assert TARGETS==("atari_2600","apple_ii","windows_95")
    assert len(set(COMPILERS.values()))==3
    assert set(OUTPUTS)==set(TARGETS)
    assert COMPILERS["atari_2600"]=="dasm"
    assert COMPILERS["apple_ii"]=="cl65"
    assert COMPILERS["windows_95"]=="i686-w64-mingw32-gcc"

def _mock_atari_rom():
    code=bytearray(4096)
    code[0]=0x78 # 6502 SEI
    code[-4:]=b"\x00\xf0\x00\xf0"
    return bytes(code)

def _mock_windows_pe():
    data=bytearray(768)
    data[:2]=b"MZ"
    data[0x3c:0x40]=(0x80).to_bytes(4,"little")
    data[0x80:0x84]=b"PE\x00\x00"
    data[0x84:0x86]=(0x14c).to_bytes(2,"little")
    data[0x80+24:0x80+26]=(0x10b).to_bytes(2,"little")
    data[0x80+24+68:0x80+24+70]=(2).to_bytes(2,"little")
    return bytes(data)

def test_byte_level_validation_is_not_filename_based():
    assert identify_binary("atari_2600",_mock_atari_rom())=="atari2600_6507_4k"
    assert identify_binary("apple_ii",bytes([0x20,0x00,0xC0])*200)=="apple2_prodos_loadable"
    assert identify_binary("windows_95",_mock_windows_pe())=="win32_i386_pe32_gui"
    for target,bad in [
      ("atari_2600",b"MZ"+bytes(100)),
      ("atari_2600",bytes(4096)),
      ("atari_2600",_mock_atari_rom()[:-1]),
      ("apple_ii",b"MZ"+bytes(550)),
      ("apple_ii",b"PK\x03\x04"+bytes(550)),
      ("apple_ii",b"bad"),
      ("windows_95",bytes(768)),
      ("windows_95",_mock_atari_rom()),
      ("windows_95",_mock_windows_pe()[:100]),
      ("windows_95",_mock_windows_pe()[:0x80+24]+b"\x0b\x02"+
        _mock_windows_pe()[0x80+26:]),
    ]:
        with pytest.raises(ValueError):
            identify_binary(target,bad)
    with pytest.raises(ValueError):
        identify_binary("ios",_mock_windows_pe())

@pytest.mark.parametrize("bad",[
  "", "/etc/shadow","../repo",r"root\..\shadow","foo//../bar",
])
def test_archive_entries_fail_closed_on_traversal(bad):
    if bad=="": # invalid no-member entry
        with pytest.raises(ValueError):
            _member(bad,b"demo")
    else:
        with pytest.raises(ValueError):
            _member(bad,b"demo")

def test_existing_artifact_directory_never_overwritten(tmp_path):
    root=tmp_path/"games"
    root.mkdir()
    (root/"existing").write_text("private data")
    with pytest.raises(ValueError,match="empty"):
        build_original_hardware(root)
    assert (root/"existing").read_text()=="private data"

@pytest.mark.parametrize("invalid",[True,False,-1,2**32,3.5,"3"])
def test_cross_compile_does_not_accept_invalid_seed(tmp_path,invalid):
    with pytest.raises(ValueError,match="seed"):
        build_original_hardware(tmp_path/"new",seed=invalid)

def test_three_real_compilers_generate_deterministic_provenance_archive(tmp_path):
    missing=[name for name in COMPILERS.values() if not shutil.which(name)]
    if missing or not shutil.which("make"):
        pytest.skip("native cross toolchains not installed: "+", ".join(missing))
    result=build_original_hardware(tmp_path/"original",seed=2600)
    assert result["schema"]=="skeleton.ai.dragon.historical_release_envelope.v1"
    assert not result["gameplay_playtested"]
    assert not result["device_compatible"]
    assert not result["release_approved"]
    assert len(result["records"])==3
    path=tmp_path/"original"/"dragon-original-hardware-compiled.zip"
    assert sha256(path.read_bytes()).hexdigest()==result["archive_sha256"]
    assert path.stat().st_size==result["archive_size"]
    with ZipFile(path) as archive:
        assert "release-evidence.json" in archive.namelist()
        proof=archive.read("release-evidence.json")
        assert sha256(proof).hexdigest()==result["evidence_sha256"]
        manifest=json.loads(proof)
        assert manifest["compiler_pass_count"]==3
        assert manifest["emulator_controller_verified_count"]==0
        assert manifest["physical_hardware_verified_count"]==0
        assert manifest["distribution_approval_count"]==0
        assert manifest["targets"]==list(TARGETS)
        for record in result["records"]:
            assert record["native_compiler_pass"]
            assert not record["emulator_gameplay_pass"]
            assert not record["physical_hardware_pass"]
            assert not record["legal_distribution_approved"]
            assert len(record["source_manifest_sha256"])==64
            assert record["source_file_count"]>=3
            assert len(record["compiler_signature_sha256"])==64
            target=record["target"]
            image=archive.read(target+"/"+record["artifact_name"])
            assert len(image)==record["artifact_bytes"]
            assert sha256(image).hexdigest()==record["artifact_sha256"]
            assert identify_binary(target,image)==record["binary_format"]
            assert (tmp_path/"original"/target/record["artifact_name"]).read_bytes()==image
            assert target+"/source/src/main." + (
                "asm" if target=="atari_2600" else "c"
            ) in archive.namelist()
    with pytest.raises(ValueError,match="empty"):
        build_original_hardware(tmp_path/"original",seed=2600)
