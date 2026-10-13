"""Real 6502 compiler receipts and source/binary archive integrity."""
from __future__ import annotations
from dataclasses import asdict
from hashlib import sha256
from zipfile import ZipFile
from pathlib import Path
import json,shutil
import pytest
from skeleton.ai.webcrawler.dragon_cc65_release import (
    compile_classics,_safe_member,_lib_present,ClassicBuildReceipt,
)
from skeleton.ai.webcrawler.dragon_native_cc65_classics import CLASSICS

def test_classic_compiler_artifact_rejects_archive_path_traversal():
    for x in ("../secret","/tmp/result","a/../../bad"):
        with pytest.raises(ValueError):
            _safe_member(x,b"hello")
    info,data=_safe_member("game/build/output.bin",b"hello")
    assert info.filename=="game/build/output.bin"
    assert data==b"hello"
    assert info.date_time==(1980,1,1,0,0,0)

def test_real_original_cc65_native_bundle_and_source_identity(tmp_path):
    if not shutil.which("cl65") or not shutil.which("make"):
        pytest.skip("real cc65 compiler is absent")
    root=tmp_path/"classic-native-release"
    receipts=compile_classics(root)
    assert len(receipts)==len(CLASSICS)==4
    assert {r.target for r in receipts}==set(CLASSICS)
    assert all(isinstance(r,ClassicBuildReceipt) for r in receipts)
    assert all(r.source_fingerprint and len(r.source_fingerprint)==64 for r in receipts)
    assert all(r.compiler_signature_sha256 and len(r.compiler_signature_sha256)==64
               for r in receipts)
    for r in receipts:
        assert r.schema=="skeleton.ai.dragon.cc65_build_receipt.v1"
        assert r.compiled_artifact.startswith(r.target+"/build/")
        assert r.artifact_size>128
        assert not r.emulator_verified and not r.device_verified
        assert r.scope.endswith("no emulator or hardware evidence")
        assert sha256((root/r.compiled_artifact).read_bytes()).hexdigest()==r.artifact_sha256
        assert sha256((root/r.target/"src/main.c").read_bytes()).hexdigest()==r.source_sha256
        if not r.target_library_present:
            assert r.status=="native_6502_object_compiled_unlinked"
            assert r.compiled_artifact.endswith(".o")
        else:
            assert r.status=="native_6502_program_linked"
            assert r.compiled_artifact.endswith("."+CLASSICS[r.target].output)
        evidence=json.loads((root/r.target/"dragon-cc65-build-receipt.json").read_text())
        assert evidence==asdict(r)
    manifest=json.loads((root/"dragon-cc65-build-bundle.json").read_text())
    assert manifest["schema"]=="skeleton.ai.dragon.cc65_bundle.v1"
    assert manifest["linked_count"]+manifest["unlinked_count"]==4
    assert not manifest["emulator_or_physical_play_confirmed"]
    z=root/"dragon-original-cc65-builds.zip"
    assert z.is_file()
    with ZipFile(z) as archive:
        assert len(archive.namelist())==1+len(CLASSICS)*5
        assert json.loads(archive.read("dragon-cc65-build-bundle.json"))==manifest
        for r in receipts:
            assert sha256(archive.read(r.compiled_artifact)).hexdigest()==r.artifact_sha256
            assert sha256(archive.read(r.target+"/src/main.c")).hexdigest()==r.source_sha256
    with pytest.raises(ValueError,match="empty"):
        compile_classics(root)

def test_no_bbc_linker_promotion_if_runtime_missing(tmp_path):
    if not shutil.which("cl65"):
        pytest.skip("cc65 compiler missing")
    present=_lib_present(CLASSICS["bbc_micro"].cc65)
    assert isinstance(present,bool)
    # Never substitute a different system's libc or mark the BBC
    # ROM/binary complete from the presence of the compiler command.
    assert CLASSICS["bbc_micro"].cc65=="bbc"
