"""Original game source ZIP: real owner attestation and verified contents."""
from __future__ import annotations
from io import BytesIO
from zipfile import ZipFile
from base64 import b64decode
import json
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from routes import dragon_academy as route


def editor():
    return route._native_source_editor({
        "email":"original-world-owner@example.test",
        "role":"editor","tenant_id":"game-studio-originals",
    })


@pytest.mark.parametrize("target",[
    "game_boy","game_boy_color","nes","snes","pc_linux",
])
def test_source_export_actually_emits_original_platform_world_art_and_receipts(target):
    data=route.native_world_codex_source_bundle(
        route.NativeCodexBundleRequest(
            index="0",target=target,chunks=2,rights_attested=True,
        ),owner=editor())
    assert data["ok"]
    assert data["filename"].endswith("-"+target+".zip")
    assert data["independent_source_verification"]["verified"]
    assert data["source_bundle"]["rights_attested"]
    assert not data["source_bundle"]["game_binary_included"]
    assert not data["independent_source_verification"]["game_binary_present"]
    blob=b64decode(data["archive_base64"],validate=True)
    assert len(blob)==data["source_bundle"]["compressed_bytes"]
    with ZipFile(BytesIO(blob)) as z:
        name_set=set(z.namelist())
        assert "RELEASE_MANIFEST.json" in name_set
        assert "art/original-tiles.bin" in name_set
        assert "world/original-world.json" in name_set
        assert "story/original-narrative-rules.json" in name_set
        report=json.loads(z.read("RELEASE_MANIFEST.json"))
        assert report["rights_attested"]
        assert not report["actual_native_compilation_verified"]
        if target=="pc_linux":
            assert "src/dragon_codex_game.c" in name_set
        else:
            assert "src/dragon_codex_game.c" not in name_set


def test_author_must_explicitly_attest_rights_before_exporting_games():
    with pytest.raises(HTTPException) as blocked:
        route.native_world_codex_source_bundle(
            route.NativeCodexBundleRequest(
                index="0",target="nes",rights_attested=False),
            owner=editor(),
        )
    assert blocked.value.status_code==403


def test_unknown_target_must_never_create_a_false_console_project():
    with pytest.raises(HTTPException) as denied:
        route.native_world_codex_source_bundle(
            route.NativeCodexBundleRequest(
                index="0",target="imagined_unlicensed_console",
                rights_attested=True,
            ),owner=editor())
    assert denied.value.status_code==422


@pytest.mark.parametrize("invalid",[
    {"rights_attested":1},
    {"rights_attested":"yes"},
    {"target":"retail/bios"},
    {"chunks":0},{"chunks":5},{"chunks":True},
    {"index":7},{"index":"001"},
    {"external_asset_payload":"invalid"},
])
def test_codex_source_ZIP_inputs_refuse_coercion_or_untrusted_content(invalid):
    with pytest.raises(ValidationError):
        route.NativeCodexBundleRequest(**invalid)


def test_untrusted_viewer_cannot_publish_or_export_original_content():
    path="/api/dragon-academy/native/production/worlds/codex/source-bundle"
    definition=next(x for x in route.router.routes if x.path==path)
    assert any(dep.call is route._native_source_editor
               for dep in definition.dependant.dependencies)
    with pytest.raises(HTTPException) as denied:
        route._native_source_editor({
            "email":"viewer@example.invalid","role":"viewer",
            "tenant_id":"game-studio-originals",
        })
    assert denied.value.status_code==403
