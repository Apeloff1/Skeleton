"""Reproducible real Atari Lynx native cartridge and source-bound build report."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json,shutil
import pytest

from skeleton.ai.webcrawler.dragon_lynx_release import build_lynx_cartridge
from skeleton.ai.webcrawler.dragon_native_lynx import lynx_source

def test_original_lynx_source_is_seeded_and_bounded_without_host_side_effects():
    src=lynx_source(2026)
    assert set(src)=={"src/main.c","Makefile","README.port.md"}
    assert "#include <lynx.h>" in src["src/main.c"]
    assert "tgi_install(tgi_static_stddrv)" in src["src/main.c"]
    assert "joy_read(JOY_1)" in src["src/main.c"]
    assert "__SEED__" not in src["src/main.c"]
    assert src==lynx_source(2026)
    assert src!=lynx_source(1989)

def test_lynx_cartridge_builder_refuses_existing_or_linked_output(tmp_path):
    if not shutil.which("cl65") or not shutil.which("make"):
        pytest.skip("cc65 toolchain not installed")
    existing=tmp_path/"existing"
    existing.mkdir()
    (existing/"untrusted").write_text("preserve")
    with pytest.raises(ValueError,match="empty"):
        build_lynx_cartridge(existing)
    assert (existing/"untrusted").read_text()=="preserve"
    link=tmp_path/"linked"
    link.symlink_to(existing,target_is_directory=True)
    with pytest.raises(ValueError,match="symlink"):
        build_lynx_cartridge(link)

def test_compiled_lynx_is_real_lnx_with_deterministic_source_and_hashes(tmp_path):
    if not shutil.which("cl65") or not shutil.which("make"):
        pytest.skip("cc65 toolchain not installed")
    root=tmp_path/"native"
    r=build_lynx_cartridge(root,seed=2026)
    assert r.native_compiler_pass
    assert r.lynx_header_magic=="LYNX"
    assert r.lynx_header_version in (1,2)
    assert not r.emulator_controller_replay_pass
    assert not r.real_hardware_pass
    assert not r.physical_audio_verified
    assert not r.distribution_approved
    binary=(root/"build"/"dragon.lnx").read_bytes()
    assert binary.startswith(b"LYNX")
    assert sha256(binary).hexdigest()==r.cartridge_sha256
    assert r.cartridge_bytes==len(binary)
    source=(root/"src"/"main.c").read_bytes()
    assert sha256(source).hexdigest()==r.source_sha256
    pkg=root/"dragon-original-lynx.zip"
    assert sha256(pkg.read_bytes()).hexdigest()==r.package_sha256
    receipt=json.loads((root/"dragon-lynx-release.json").read_text())
    assert receipt["cartridge_sha256"]==r.cartridge_sha256
    with ZipFile(pkg) as z:
        assert set(z.namelist())=={
           "dragon.lnx","src/main.c","Makefile",
           "source-compile-receipt.json","README.txt"}
        assert z.read("dragon.lnx")==binary
        assert sha256(z.read("src/main.c")).hexdigest()==r.source_sha256
        internal=json.loads(z.read("source-compile-receipt.json"))
        assert internal["cartridge_sha256"]==r.cartridge_sha256
        assert internal["emulator_controller_replay_pass"] is False
