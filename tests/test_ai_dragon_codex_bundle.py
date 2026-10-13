"""Actual deterministic original console/PC game-source ZIP deliverables."""
from __future__ import annotations
from dataclasses import replace
from io import BytesIO
from zipfile import ZipFile
import json,subprocess,shutil
import pytest

from skeleton.ai.webcrawler.dragon_world_codex import unrank,edit
from skeleton.ai.webcrawler.dragon_codex_bundle import (
    SCHEMA,publish_codex_source,verify_codex_source,
)


@pytest.mark.parametrize("target",[
    "game_boy","game_boy_color","nes","snes",
    "pc_linux","pc_windows","pc_macos","steam_deck",
])
def test_original_content_source_bundle_is_deterministic_and_verified(target):
    source=edit("0",{
        "storm_fronts":255,"story_branching":155,
        "secret_density":190,"world_repopulation":220,
    })
    bundle=publish_codex_source(
        source,target,chunks=2,rights_attested=True,
    )
    assert bundle.schema==SCHEMA
    assert bundle.rights_attested
    assert not bundle.game_binary_included
    assert not bundle.native_project_compilation_verified
    assert bundle.source_content_verified
    assert bundle.compressed_bytes==len(bundle.zip_bytes)
    assert bundle==publish_codex_source(
        source,target,chunks=2,rights_attested=True)
    assert verify_codex_source(source,bundle,chunks=2)["verified"]
    with ZipFile(BytesIO(bundle.zip_bytes)) as z:
        members=set(z.namelist())
        assert members==set(bundle.source_members)
        assert "RELEASE_MANIFEST.json" in members
        assert "art/original-tiles.bin" in members
        assert "world/original-world.json" in members
        assert "story/original-narrative-rules.json" in members
        manifest=json.loads(z.read("RELEASE_MANIFEST.json"))
        assert manifest["rights_attested"]
        assert not manifest["game_binary_included"]
        assert not manifest["actual_native_compilation_verified"]
        assert len(manifest["source_members"])>=5
        if target in ("pc_linux","pc_windows","pc_macos","steam_deck"):
            assert "src/dragon_codex_game.c" in members
        else:
            assert "src/dragon_codex_game.c" not in members
        assert not any(name.endswith((".exe",".gb",".nes",".rom",
                                      ".elf",".dll")) for name in members)


def test_source_release_requires_explicit_owner_rights_attestation():
    with pytest.raises(PermissionError):
        publish_codex_source(unrank("0"),"game_boy")
    with pytest.raises(PermissionError):
        publish_codex_source(
            unrank("0"),"pc_linux",rights_attested=1)


def test_forged_rights_game_binary_or_copyrighted_source_are_rejected():
    source=unrank("0")
    artifact=publish_codex_source(
        source,"nes",rights_attested=True)
    with pytest.raises(ValueError):
        verify_codex_source(
            source,replace(artifact,game_binary_included=True))
    with pytest.raises(ValueError):
        verify_codex_source(
            source,replace(artifact,zip_bytes=b"not a game source archive"))
    with pytest.raises(ValueError):
        verify_codex_source(
            edit("0",{"story_branching":1}),artifact)
    with pytest.raises(ValueError):
        publish_codex_source(
            source,"not_a_licensed_console",rights_attested=True)


def test_content_source_bundles_contain_different_real_hardware_tiles():
    src=unrank("0")
    gb=publish_codex_source(src,"game_boy",rights_attested=True)
    nes=publish_codex_source(src,"nes",rights_attested=True)
    snes=publish_codex_source(src,"snes",rights_attested=True)
    with ZipFile(BytesIO(gb.zip_bytes)) as a, (
         ZipFile(BytesIO(nes.zip_bytes)) as b), (
         ZipFile(BytesIO(snes.zip_bytes)) as c):
        asset_gb=a.read("art/original-tiles.bin")
        asset_nes=b.read("art/original-tiles.bin")
        asset_snes=c.read("art/original-tiles.bin")
    assert len(asset_gb)==len(asset_nes)==12*16
    assert len(asset_snes)==12*32
    assert asset_gb!=asset_nes
    assert asset_nes!=asset_snes


@pytest.mark.skipif(shutil.which("cc") is None,
                    reason="native C99 compiler unavailable")
def test_exported_desktop_game_source_can_actually_compile_and_finish_selftest(tmp_path):
    address=edit("0",{"elevation_tectonics":255})
    release=publish_codex_source(
        address,"pc_linux",rights_attested=True)
    with ZipFile(BytesIO(release.zip_bytes)) as z:
        c=tmp_path/"dragon_codex_game.c"
        c.write_bytes(z.read("src/dragon_codex_game.c"))
    binary=tmp_path/"world"
    result=subprocess.run([
        "cc","-std=c99","-Wall","-Wextra","-Werror",
        str(c),"-o",str(binary),
    ],capture_output=True,text=True,timeout=25)
    assert result.returncode==0,result.stderr
    checked=subprocess.run(
        [str(binary),"--selftest"],
        capture_output=True,text=True,timeout=15)
    assert checked.returncode==0,checked.stderr
    assert checked.stdout.count("PROVED ")==16
    assert "DRAGON_CODEX_SELFTEST_PASS" in checked.stdout


def test_source_archive_with_extra_chunks_does_not_fake_the_original_receipt():
    source=edit("0",{"story_branching":200})
    product=publish_codex_source(
        source,"game_boy",chunks=3,rights_attested=True)
    assert verify_codex_source(source,product,chunks=3)["verified"]
    with pytest.raises(ValueError):
        verify_codex_source(source,product,chunks=1)
