"""Dragon Academy product routes: real auth, tenant isolation and offline artifacts."""
from __future__ import annotations

import hashlib
import sqlite3

import pytest
from fastapi import HTTPException

from core.routes_registry import KNOWN_ROUTES
from routes import dragon_academy as route
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_practice_lab import ApprovedLesson,DragonPracticeLab


def identity(email="alice@example.test", tenant="tenant-a"):
    return route._principal({"email":email,"tenant_id":tenant,"role":"viewer"})


def approved(owner):
    decision=PromotionDecision(
        "claim-physics", True, .99,"calibrated",None,(),
        hashlib.sha256(b"evidence").hexdigest(),
    )
    return ApprovedLesson(owner, "Gravity and collisions",decision,"a"*64,
        (Mechanic.MOVEMENT,Mechanic.PLATFORMING,Mechanic.PHYSICS),
        True,
    )


def test_registered_with_existing_auth_and_no_authority_mint_endpoints():
    assert ("routes.dragon_academy","router") in KNOWN_ROUTES
    paths={r.path for r in route.router.routes}
    assert "/api/dragon-academy/status" in paths
    assert "/api/dragon-academy/practice/run" in paths
    assert "/api/dragon-academy/practice/subscribe" in paths
    assert not any("offer" in p or "approve" in p or "xp" in p or "review" in p
                   for p in paths)
    assert '/api/dragon-academy/native/generate' in paths
    assert '/api/dragon-academy/native/targets' in paths


@pytest.mark.parametrize("user",[
    None,{},{"email":"foo@example.test","role":"viewer","dev_mode":True},
    {"email":"foo@example.test","role":"unknown"},
    {"email":"foo@example.test","tenant_id":"","role":"editor","disabled":True},
])
def test_missing_or_anonymous_principal_cannot_access_practice(user):
    with pytest.raises(HTTPException) as err:
        route._principal(user)
    assert err.value.status_code in (401,403)


def test_principal_is_tenant_scoped_and_not_request_controllable():
    assert identity()==identity()
    assert identity()!=identity("bob@example.test")
    assert identity()!=identity(tenant="tenant-b")
    assert len(identity())==64
    with pytest.raises(HTTPException):
        route._principal({"email":"alice@example.test","tenant_id":123,"role":"viewer"})


def test_storage_is_fail_closed(monkeypatch):
    monkeypatch.delenv("SKL_DRAGON_PRACTICE_DB_PATH",raising=False)
    with pytest.raises(HTTPException) as exc:
        route.academy_status(owner=identity())
    assert exc.value.status_code==503


def test_real_playable_artifact_is_only_returned_as_data(tmp_path,monkeypatch):
    db_path=tmp_path/"dragon-practice.sqlite"
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(db_path))
    owner=identity()
    with sqlite3.connect(db_path) as db:
        DragonPracticeLab(db).offer(approved(owner),authorized=True,now=10)
    first=route.academy_status(owner=owner)
    assert first["progress"]["xp"]==30
    assert first["progress"]["level"]==1
    assert first["attempts"]==[]
    result=route.run_practice(route.RunPracticeRequest(max_demos=2),owner=owner)
    assert len(result["created"])==2
    assert result["progress"]["demos_built"]==2
    assert result["progress"]["xp"]==30  # generating alone never gains XP
    demo=result["created"][0]
    artifact=route.practice_artifact(demo["attempt_id"],owner=owner)
    assert artifact["sandbox_required"] is True
    assert artifact["sha256"]==demo["artifact_digest"]
    assert hashlib.sha256(artifact["html"].encode()).hexdigest()==artifact["sha256"]
    assert "<canvas" in artifact["html"]
    assert 'data-key="KeyA"' in artifact["html"]
    with pytest.raises(HTTPException) as denied:
        route.practice_artifact(demo["attempt_id"],owner=identity("bob@example.test"))
    assert denied.value.status_code==404
    second=route.academy_status(owner=owner)
    assert second["progress"]["demo_attempts"]==2


def test_subscription_requires_explicit_confirm_and_stops(tmp_path,monkeypatch):
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(tmp_path/"academy.sqlite"))
    owner=identity()
    with pytest.raises(HTTPException) as missing:
        route.subscribe_practice(route.SubscribeRequest(approved=False),owner=owner)
    assert missing.value.status_code==403
    sub=route.subscribe_practice(route.SubscribeRequest(
        approved=True,hours=24,max_ticks=3,demos_per_tick=2),owner=owner)
    assert sub["subscription"]["enabled"]
    assert sub["subscription"]["remaining_ticks"]==3
    stopped=route.stop_practice(owner=owner)
    assert not stopped["subscription"]["enabled"]
    assert stopped["progress"]["xp"]==0
    with sqlite3.connect(tmp_path/"academy.sqlite") as db:
        lab=DragonPracticeLab(db)
        original=lab.offer(approved(owner),authorized=True,now=9)
    stop_again=route.stop_practice(owner=owner)
    assert stop_again["progress"]["verified_lessons"]==1
    revoked=route.revoke_practice(owner=owner)
    assert not revoked["subscription"]["enabled"]
    assert route.run_practice(route.RunPracticeRequest(max_demos=2),owner=owner)["created"]==[]
    with sqlite3.connect(tmp_path/"academy.sqlite") as db:
        lab=DragonPracticeLab(db)
        assert lab.offer(approved(owner),authorized=True,now=12)==original
    # Regranting the same reviewed claim does not double XP.
    assert route.academy_status(owner=owner)["progress"]["xp"]==30
    with pytest.raises(HTTPException) as not_found:
        route.practice_artifact("b"*64,owner=owner)
    assert not_found.value.status_code==404


def test_native_console_source_is_downloadable_by_authenticated_owner_only(
    tmp_path,monkeypatch,
):
    from zipfile import ZipFile
    from io import BytesIO
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(tmp_path/"native.sqlite"))
    owner=identity("alice@example.test")
    with sqlite3.connect(tmp_path/"native.sqlite") as db:
        DragonPracticeLab(db).offer(approved(owner),authorized=True,now=2)
    targets=route.native_targets(owner=owner)
    assert len(targets["targets"])>=45
    assert any(t["id"]=="game_boy" for t in targets["targets"])
    created=route.generate_native(route.NativeGenerateRequest(
        target_id="game_boy",style="arcade_score_attack"),owner=owner)
    item=created["created_native"]
    assert item["state"]=="source_generated"
    assert created["progress"]["xp"]==30
    response=route.native_archive(item["attempt_id"],owner=owner)
    assert response.media_type=="application/zip"
    with ZipFile(BytesIO(response.body)) as z:
        assert "src/main.asm" in z.namelist()
        assert "Makefile" in z.namelist()
        assert "dragon-native-manifest.json" in z.namelist()
        assert "rgbasm" in z.read("Makefile").decode()
    assert hashlib.sha256(response.body).hexdigest()==response.headers["x-content-sha256"]
    with pytest.raises(HTTPException) as denied:
        route.native_archive(item["attempt_id"],owner=identity("bob@example.test"))
    assert denied.value.status_code==404
    with pytest.raises(HTTPException) as denied_sdk:
        route.generate_native(route.NativeGenerateRequest(
            target_id="xbox_series",style="racing"),owner=owner)
    assert denied_sdk.value.status_code==403

def test_new_subscriptions_produce_native_projects_not_html(
    tmp_path,monkeypatch,
):
    from skeleton.ai.webcrawler.dragon_practice_cycles import DragonPracticeCycles
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(tmp_path/"native.sqlite"))
    owner=identity()
    with sqlite3.connect(tmp_path/"native.sqlite") as db:
        parent=DragonPracticeLab(db)
        parent.offer(approved(owner),authorized=True,now=3)
    scheduled=route.subscribe_practice(route.SubscribeRequest(
        approved=True,max_ticks=2,demos_per_tick=2,native_target="game_boy"),
        owner=owner)
    assert scheduled["subscription"]["generation_mode"]=="native"
    with sqlite3.connect(tmp_path/"native.sqlite") as db:
        parent=DragonPracticeLab(db)
        cycles=DragonPracticeCycles(db,parent)
        emitted=cycles.pulse(owner,authorized=True,now=scheduled["subscription"]["next_due"])
    assert emitted and emitted[0].target_id=="game_boy"
    snapshot=route.academy_status(owner=owner)
    assert snapshot["native_attempts"] and snapshot["attempts"]==[]
    assert snapshot["progress"]["xp"]==30


def test_native_build_evidence_route_never_allows_browser_to_mint_builds(
    tmp_path,monkeypatch,
):
    from skeleton.ai.webcrawler.dragon_native_practice import DragonNativePracticeLab
    from skeleton.ai.webcrawler.dragon_build_evidence import DragonBuildEvidence
    path=tmp_path/"builds.sqlite"
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(path))
    monkeypatch.delenv("SKL_DRAGON_BUILD_SIGNING_KEY_HEX",raising=False)
    owner=identity()
    with sqlite3.connect(path) as db:
        parent=DragonPracticeLab(db)
        parent.offer(approved(owner),authorized=True,now=1)
        native=DragonNativePracticeLab(db,parent)
        attempt=native.generate(owner,target_id="nes",style="arcade_score_attack",
                                authorized=True,consent=True,now=2)
        key=bytes.fromhex("ab"*32)
        signer=DragonBuildEvidence(db,native,private_signing_key=key)
        fixture=bytearray(16+32768+8192)
        fixture[:6]=b"NES\x1a\x02\x01"
        signer.attest_rom(owner,attempt.attempt_id,bytes(fixture),
                          toolchain="cc65",trusted_worker=True,
                          authorized=True,now=3)
    with pytest.raises(HTTPException) as not_ready:
        route.native_build_evidence(owner=owner)
    assert not_ready.value.status_code==503
    monkeypatch.setenv("SKL_DRAGON_BUILD_SIGNING_KEY_HEX","ab"*32)
    result=route.native_build_evidence(owner=owner)
    assert result["ok"] and len(result["receipts"])==1
    assert result["receipts"][0]["source_digest"]==attempt.source_digest
    assert "not executed gameplay" in result["claim_boundary"]
    assert route.native_build_evidence(owner=identity("other@example.test"))["receipts"]==[]
    paths={r.path for r in route.router.routes}
    assert "/api/dragon-academy/native/evidence" in paths
    assert not any("attest" in x or "mint-build" in x for x in paths)


def test_native_curriculum_backend_is_consent_bound_and_owner_scoped(
    tmp_path,monkeypatch,
):
    path=tmp_path/"curriculum.sqlite"
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(path))
    monkeypatch.delenv("SKL_DRAGON_BUILD_SIGNING_KEY_HEX",raising=False)
    owner=identity()
    with sqlite3.connect(path) as db:
        parent=DragonPracticeLab(db)
        parent.offer(approved(owner),authorized=True,now=1)
    before=route.native_curriculum(owner=owner)
    assert before["ok"] and before["curriculum_level"]==1
    assert before["next_recommendation"]["target"]=="game_boy"
    with pytest.raises(HTTPException) as denied:
        route.native_curriculum_generate(route.CurriculumGenerateRequest(
            approved=False),owner=owner)
    assert denied.value.status_code==403
    accepted=route.native_curriculum_generate(route.CurriculumGenerateRequest(
        approved=True),owner=owner)
    assert accepted["created_native"]["target_id"]=="game_boy"
    assert accepted["curriculum"]["native_source_attempts"]==1
    assert accepted["progress"]["xp"]==30
    assert route.native_curriculum(owner=identity("another@example.test"))[
        "native_source_attempts"]==0
    paths={item.path for item in route.router.routes}
    assert "/api/dragon-academy/native/curriculum" in paths
    assert "/api/dragon-academy/native/curriculum/generate" in paths


def test_adaptive_practice_subscriptions_preserve_opt_in_and_finite_ticks(
    tmp_path,monkeypatch,
):
    from skeleton.ai.webcrawler.dragon_practice_cycles import DragonPracticeCycles
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(tmp_path/"adaptive.sqlite"))
    monkeypatch.delenv("SKL_DRAGON_BUILD_SIGNING_KEY_HEX",raising=False)
    owner=identity()
    with sqlite3.connect(tmp_path/"adaptive.sqlite") as db:
        DragonPracticeLab(db).offer(approved(owner),authorized=True,now=1)
    subscription=route.subscribe_practice(route.SubscribeRequest(
        approved=True,adaptive=True,max_ticks=2,demos_per_tick=1),owner=owner)
    assert subscription["subscription"]["generation_mode"]=="curriculum"
    with sqlite3.connect(tmp_path/"adaptive.sqlite") as db:
        lab=DragonPracticeLab(db)
        cycles=DragonPracticeCycles(db,lab)
        created=cycles.pulse(
            owner,authorized=True,now=subscription["subscription"]["next_due"])
    assert len(created)==1
    assert created[0].target_id=="game_boy"
    assert route.academy_status(owner=owner)["native_attempts"]



def test_creator_source_bundle_auth_requires_editor_and_no_dev_bypass():
    for user in (
        None,
        {"email": "a@example.test", "role": "editor", "dev_mode": True},
        {"email": "a@example.test", "role": "viewer"},
    ):
        with pytest.raises(HTTPException) as denied:
            route._native_source_editor(user)
        assert denied.value.status_code in (401, 403)
    good = {"email": "maker@example.test", "tenant_id": "studio-x", "role": "editor"}
    assert route._native_source_editor(good) == route._principal(good)


def test_creator_bundle_emits_real_native_source_without_build_or_database():
    from io import BytesIO
    from zipfile import ZipFile
    from skeleton.ai.webcrawler.dragon_native_production import verify_source_bundle

    owner = identity()
    catalog = route.native_production_capabilities(owner=owner)
    assert catalog["ok"]
    assert any(x["id"] == "game_boy" and x["native_source_emitter"]
               for x in catalog["targets"])
    assert all("certificate" not in str(x.get("claims", "")).lower()
               for x in catalog["targets"])

    body = route.NativeProductionSourceRequest(
        title="Original Lunar Drifter",
        style="arcade_score_attack", targets=["game_boy", "nes"],
        original_work_attested=True, approved=True,
    )
    response = route.native_production_source_bundle(body, owner=owner)
    assert response.media_type == "application/zip"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-dragon-claim"] == "source-only-not-a-compiled-game"
    assert hashlib.sha256(response.body).hexdigest() == response.headers["x-content-sha256"]
    audit = verify_source_bundle(response.body)
    assert audit["status"] == "verified_source_bundle"
    assert audit["target_count"] == 2
    with ZipFile(BytesIO(response.body)) as payload:
        assert "production-index.json" in payload.namelist()
        assert sum(x.startswith("releases/dragon-") for x in payload.namelist()) == 2


def test_creator_bundle_fail_closed_on_rights_and_unimplemented_platform():
    owner = identity()
    no_rights = route.NativeProductionSourceRequest(
        title="Original Lantern", style="arcade_score_attack",
        targets=["game_boy"], original_work_attested=False, approved=True,
    )
    with pytest.raises(HTTPException) as denied:
        route.native_production_source_bundle(no_rights, owner=owner)
    assert denied.value.status_code == 403

    unsupported = route.NativeProductionSourceRequest(
        title="Original Lantern", style="arcade_score_attack",
        targets=["ps5"], original_work_attested=True, approved=True,
    )
    with pytest.raises(HTTPException) as denied:
        route.native_production_source_bundle(unsupported, owner=owner)
    assert denied.value.status_code == 422

    no_publication = route.NativeProductionSourceRequest(
        title="Original Lantern", style="arcade_score_attack",
        targets=["game_boy"], original_work_attested=True, approved=False,
    )
    with pytest.raises(HTTPException) as denied:
        route.native_production_source_bundle(no_publication, owner=owner)
    assert denied.value.status_code == 403



@pytest.mark.parametrize("changes", [
    {"approved": 1},
    {"approved": "true"},
    {"original_work_attested": 1},
    {"original_work_attested": "yes"},
    {"seed": True},
    {"seed": "1"},
    {"compile_roms": True},
    {"allow_licensed_sdk": True},
    {"targets": ["game_boy"] * 4},
])
def test_native_creator_request_rejects_coerced_authority_and_extra_fields(changes):
    from pydantic import ValidationError
    payload = {
        "title": "Original River Quest",
        "style": "arcade_score_attack",
        "targets": ["game_boy"],
        "original_work_attested": True,
        "approved": True,
    }
    payload.update(changes)
    with pytest.raises(ValidationError):
        route.NativeProductionSourceRequest(**payload)



def test_native_creator_portable_design_is_downloaded_as_original_native_source():
    from zipfile import ZipFile
    from io import BytesIO
    import json
    from skeleton.ai.webcrawler.dragon_native_production import verify_source_bundle

    approved = route.NativeProductionSourceRequest(
        title="Original Galaxy Puzzle", style="arcade_score_attack",
        targets=["game_boy", "pc_linux"],
        original_work_attested=True, approved=True, seed=337,
        portable_design=route.NativeProductionDesignBody(
            palette="modern_neon", hero="astronaut", quest_theme="space",
            difficulty=8, stages=6, candidates=13,
        ),
    )
    response = route.native_production_source_bundle(approved, owner=identity())
    assert verify_source_bundle(response.body)["target_count"] == 2
    with ZipFile(BytesIO(response.body)) as archive:
        manifest = json.loads(archive.read("production-index.json"))
        assert manifest["target_count"] == 2
        assert all(item["port_profile_digest"] for item in manifest["entries"])
        for zip_name in archive.namelist():
            if not zip_name.startswith("releases/"):
                continue
            with ZipFile(BytesIO(archive.read(zip_name))) as nested:
                receipt = json.loads(nested.read("release-receipt.json"))
                assert receipt["port_plan"]["production_seed"] == 337
                assert receipt["port_plan"]["portable_profile"]["hero"] == "astronaut"
                assert receipt["evidence"] == "source_generated"


@pytest.mark.parametrize("fields", [
    {"portable_design": {"difficulty": 11}},
    {"portable_design": {"difficulty": True}},
    {"portable_design": {"stages": "4"}},
    {"portable_design": {"candidates": 25}},
    {"portable_design": {"hero": "hatchling", "private_script": "import os"}},
])
def test_portable_creator_api_does_not_coerce_or_execute_design(fields):
    from pydantic import ValidationError
    data = {
        "title": "Original Homebrew", "style": "arcade_score_attack",
        "targets": ["game_boy"], "approved": True, "original_work_attested": True,
    }
    data.update(fields)
    with pytest.raises(ValidationError):
        route.NativeProductionSourceRequest(**data)



def test_authenticated_creator_preview_is_read_only_and_exposes_hardware_degradations(
    monkeypatch,
):
    from skeleton.ai.webcrawler import dragon_native_production as production
    def fail_if_emitted(**kwargs):
        raise AssertionError("source emitter must never execute during preview")
    monkeypatch.setattr(production, "render_native_project", fail_if_emitted)
    body = route.NativeProductionSourceRequest(
        title="Original Trail Quest", style="arcade_score_attack",
        targets=["game_boy", "pc_linux"], approved=False,
        original_work_attested=True,
        portable_design=route.NativeProductionDesignBody(
            palette="modern_neon", hero="explorer",
            stages=6, candidates=12, difficulty=7,
        ),
    )
    result = route.native_production_preview(body, owner=identity())
    assert result["ok"]
    assert result["status"] == "source_ready"
    assert result["can_export_sources"]
    assert result["evidence"] == "none"
    assert result["candidate_count"] == 2
    rows = {item["target"]: item for item in result["targets"]}
    assert rows["game_boy"]["target_stages"] == 1
    assert rows["game_boy"]["target_palette"] == "handheld"
    assert rows["pc_linux"]["target_stages"] == 6
    assert not rows["pc_linux"]["adaptations"]


def test_native_creator_preview_cannot_bypass_original_rights_declaration():
    body = route.NativeProductionSourceRequest(
        title="Original Trail Quest", style="arcade_score_attack",
        targets=["game_boy"], approved=False, original_work_attested=False,
    )
    with pytest.raises(HTTPException) as denied:
        route.native_production_preview(body, owner=identity())
    assert denied.value.status_code == 403


def test_native_creator_preview_discloses_blocked_licensed_sdk():
    body = route.NativeProductionSourceRequest(
        title="Original Trail Quest", style="arcade_score_attack",
        targets=["game_boy", "ps5"], approved=False,
        original_work_attested=True,
    )
    report = route.native_production_preview(body, owner=identity())
    assert not report["can_export_sources"]
    assert {t["target"]: t["state"] for t in report["targets"]} == {
        "game_boy": "source_ready",
        "ps5": "blocked",
    }
    assert "no generated code" in report["claim_boundary"]



@pytest.mark.parametrize("hero,theme,palette", [
    ("hatchling", "crystals", "dmg_green"),
    ("robot", "clockwork", "modern_neon"),
    ("astronaut", "space", "vga_dusk"),
    ("pilot", "volcano", "handheld"),
    ("explorer", "forest", "cga"),
    ("knight", "ice", "crt_arcade"),
])
def test_original_native_2bpp_pixel_preview_matches_real_emitter(hero, theme, palette):
    from skeleton.ai.webcrawler.dragon_native_artforge import original_tiles
    req = route.NativeProductionPixelArtPreview(
        hero=hero, quest_theme=theme, palette=palette,
        seed=41, target="game_boy",
    )
    result = route.native_production_art_preview(req, owner=identity())
    assert result["ok"] and result["hero"] == hero
    assert result["target"] == "game_boy"
    assert len(result["frames"]) == 4
    expected = original_tiles(
        hero=hero, theme=theme, seed=41,
        palette=result["applied_palette"],
    )
    assert result["frames"]["hero"] == expected["dragon"]
    assert result["frames"]["collectible"] == expected["star"]
    assert len(result["gb_tiles_sha256"]) == 64
    assert all(set("".join(frame)) <= set("0123")
               for frame in result["frames"].values())
    assert "not certified" in result["claim_boundary"]


@pytest.mark.parametrize("changes", [
    {"target": "ps5"},
    {"target": "../../local"},
    {"hero": "third_party_famous_character"},
    {"quest_theme": "game_franchise"},
    {"palette": "unknown_video_palette"},
])
def test_original_pixel_preview_denies_nonexistent_or_unlicensed_assets(changes):
    req = route.NativeProductionPixelArtPreview(**changes)
    with pytest.raises(HTTPException) as denied:
        route.native_production_art_preview(req, owner=identity())
    assert denied.value.status_code == 422


@pytest.mark.parametrize("fields", [
    {"seed": True},
    {"seed": "42"},
    {"seed": -1},
    {"hero": "robot", "custom_rom_path": "third_party.gb"},
])
def test_original_pixel_preview_is_strictly_typed_and_has_no_unsafe_inputs(fields):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        route.NativeProductionPixelArtPreview(**fields)
