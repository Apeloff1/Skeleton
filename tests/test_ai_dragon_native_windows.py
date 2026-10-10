"""Real original Windows x64 native C99 game builds with honest evidence scope."""
from __future__ import annotations
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
import json,shutil,struct,pytest

from skeleton.ai.webcrawler.dragon_native_windows import (
    TOOL,ARGS,pe64_format,_compile_windows_game,
    verify_windows_executable,publish_windows_game,
)
from skeleton.ai.webcrawler.dragon_native_production import ProductionRequest,PortableGameDesign

def spec(**changes):
    original=ProductionRequest(
        title="Original Windows Moon Sokoban",style="fixed_screen_puzzle",
        targets=("pc_windows",),seed=37,original_work_attested=True,
        portable_design=PortableGameDesign(stages=2,difficulty=4),
    )
    return replace(original,**changes)

def fake_pe(*,wrong_machine=False,wrong_magic=False):
    blob=bytearray(4096)
    blob[:2]=b"MZ"
    struct.pack_into("<I",blob,0x3c,0x80)
    blob[0x80:0x84]=b"PE\0\0"
    struct.pack_into("<HHIIIHH",blob,0x84,
                     0x14c if wrong_machine else 0x8664,
                     2,0,0,0,0xf0,0x0002)
    struct.pack_into("<H",blob,0x98,0x10b if wrong_magic else 0x20b)
    struct.pack_into("<I",blob,0x98+16,4096)
    struct.pack_into("<I",blob,0x98+56,8192)
    return bytes(blob)

def test_native_pe_parser_requires_true_64bit_windows_executable():
    assert "PE32+" in pe64_format(fake_pe())
    with pytest.raises(ValueError):
        pe64_format(fake_pe(wrong_machine=True))
    with pytest.raises(ValueError):
        pe64_format(fake_pe(wrong_magic=True))
    for fake in (b"not a windows executable",b"MZ"+b"\0"*510,
                 fake_pe()[:256],fake_pe()+b"\0"*4_000_000):
        with pytest.raises(ValueError):
            pe64_format(fake)

def test_windows_original_game_build_must_be_explicitly_approved():
    with pytest.raises(PermissionError):
        _compile_windows_game(spec(),authorized=False)

@pytest.mark.parametrize("changes",[
    {"targets":("pc_linux",)},
    {"targets":("pc_windows","pc_macos")},
    {"style":"arcade_score_attack"},
    {"compile_roms":True},
])
def test_windows_crosscompiler_refuses_unapproved_target_or_mode(changes,monkeypatch):
    # Ensure this reaches request admission even on systems lacking MinGW.
    monkeypatch.setattr(shutil,"which",lambda name:"/usr/bin/real-compiler")
    with pytest.raises(ValueError):
        _compile_windows_game(spec(**changes),authorized=True)

@pytest.mark.skipif(not shutil.which(TOOL),
                    reason="requires installed trusted mingw-w64 cross-compiler")
def test_real_original_windows_game_cross_compiles_and_structurally_verifies(tmp_path):
    source=spec()
    body,evidence=_compile_windows_game(source,authorized=True)
    output=verify_windows_executable(body)
    assert output["status"]=="native_windows_PE_structurally_verified"
    assert output["levels_proven"]==2
    assert not output["windows_runtime_tested"]
    assert evidence["windows_runtime_verified"] is False
    assert evidence["host_execution_verified"] is False
    assert evidence["cross_compiler"]==TOOL
    assert evidence["fixed_compile_arguments"]==ARGS
    with ZipFile(BytesIO(body)) as archive:
        exe=archive.read("binary/dragon_game.exe")
        assert b"PE\0\0" in exe[:65536]
        assert pe64_format(exe)==evidence["game_format"]
    published=publish_windows_game(source,tmp_path,authorized=True)
    assert (tmp_path/published["filename"]).is_file()
    assert not published["windows_runtime_tested"]

@pytest.mark.skipif(not shutil.which(TOOL),
                    reason="requires trusted mingw-w64 cross-compiler")
def test_modified_windows_game_binary_cannot_be_rebranded_verified_source():
    source=spec()
    data,evidence=_compile_windows_game(source,authorized=True)
    with ZipFile(BytesIO(data)) as original:
        entries={name:original.read(name) for name in original.namelist()}
    entries["binary/dragon_game.exe"]=entries["binary/dragon_game.exe"]+b"\x00"
    output=BytesIO()
    with ZipFile(output,"w",ZIP_DEFLATED) as archive:
        for name,content in entries.items():
            archive.writestr(name,content)
    with pytest.raises(ValueError,match="evidence"):
        verify_windows_executable(output.getvalue())
