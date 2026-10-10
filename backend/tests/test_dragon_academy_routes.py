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


def test_authenticated_companion_reads_only_signed_current_owner_review(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from skeleton.ai.game_builder.dragon_review_store import DragonReviewStore
    from skeleton.ai.game_builder.dragon_wisdom import SquareReview, SQUARES
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH", str(tmp_path/"reviews.sqlite"))
    monkeypatch.setenv("SKL_DRAGON_REVIEW_SIGNING_KEY_HEX", (b"s"*32).hex())
    monkeypatch.setattr(route.time, "time", lambda: 21)
    squares=tuple({"id": key,"label":label,"score":70,"industry_score":None,
        "industry_delta":None,"status":"improve","comparison_state":"unknown",
        "axes":list(axes)} for key,label,axes in SQUARES)
    review=SquareReview("a"*64,"b"*64,"c"*64,"d"*64,"e"*64,None,100,100,
        squares,(),(),(),"f"*64,True,20,40)
    with sqlite3.connect(tmp_path/"reviews.sqlite") as db:
        DragonReviewStore(db,signing_key=b"s"*32).publish(identity(),review,
            now=20,expires_at=40,trusted_worker=True)
    app=FastAPI();app.include_router(route.router)
    app.dependency_overrides[route.get_current_user]=lambda: {
        "email":"alice@example.test","tenant_id":"tenant-a","role":"viewer"}
    with TestClient(app) as client:
        response=client.get("/api/dragon-academy/status")
        assert response.status_code==200
        assert response.json()["wisdom_review"]["review"]==review.to_payload()
        assert client.get("/api/dragon-academy/wisdom").json()["snapshot"]==response.json()["wisdom_review"]
        assert client.post("/api/dragon-academy/wisdom",json={"review":{}}).status_code==405
        assert client.post("/api/dragon-academy/status",json={"wisdom_review":{}}).status_code==405
        app.dependency_overrides[route.get_current_user]=lambda: {
            "email":"bob@example.test","tenant_id":"tenant-a","role":"viewer"}
        assert client.get("/api/dragon-academy/status").json()["wisdom_review"] is None
        app.dependency_overrides[route.get_current_user]=lambda: {
            "email":"alice@example.test","tenant_id":"tenant-a","role":"viewer"}
        monkeypatch.setattr(route.time,"time",lambda:40)
        assert client.get("/api/dragon-academy/status").json()["wisdom_review"] is None
        monkeypatch.setattr(route.time,"time",lambda:21)
        monkeypatch.setenv("SKL_DRAGON_REVIEW_SIGNING_KEY_HEX", (b"x"*32).hex())
        assert client.get("/api/dragon-academy/status").status_code==409
        app.dependency_overrides[route.get_current_user]=lambda: None
        assert client.get("/api/dragon-academy/status").status_code==401




def test_authenticated_hoag_and_recrawl_read_only_routes(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from skeleton.ai.game_builder.reviewed_knowledge import (
        ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
    )
    from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid

    db_path = tmp_path / "knowledge.sqlite"
    monkeypatch.delenv("SKL_DRAGON_KNOWLEDGE_DB_PATH", raising=False)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user] = lambda: {
        "email": "alice@example.test", "tenant_id": "tenant-a", "role": "viewer",
    }
    with TestClient(app) as client:
        assert client.get("/api/dragon-academy/knowledge/hoag").status_code == 503
        assert client.get("/api/dragon-academy/knowledge/recrawls").status_code == 503

    owner = identity()
    now = 1_791_638_400
    with ReviewedKnowledgeStore(db_path) as library:
        wiki = DragonWisdomPyramid(library)
        revisions = {}
        for label in ("a", "b"):
            source_id = "source-" + label
            text = "Jump timing should be predictable."
            document = ReviewedDocument(
                owner=owner, source_id=source_id,
                source_url="https://example.org/" + source_id,
                title="Original game design study", text=text,
                observed_at="2026-10-10T12:00:00Z",
                license_id="design-reference-license",
                allowed_scopes=("design_reference",),
                reviewer_id="research-reviewer-" + label,
                approved=True,
                notes=(ReviewedNote(
                    note_id="note-" + label, mechanic="platforming",
                    statement=text, start=0, end=len(text),
                    stance="supports", confidence_ppm=880_000,
                    dependence_group="publisher-" + label,
                    tags=("jump",),
                ),),
            )
            revisions[label] = library.import_document(
                document, expected_parent_digest=None, authorized=True,
            )
        brief = library.build_brief(
            owner, "jump", authorized=True, min_independent_groups=2,
        )
        decision = wiki.wiki_review(
            owner, brief, mechanic="platforming", disposition="accepted",
            independent_reviewer_id="independent-wiki-reviewer",
            review_evidence_digest="a" * 64, now=now, expires_at=now + 3600,
            authorized=True, trusted_worker=True,
        )
        wiki.promote(
            owner, decision["digest"], now=now + 1,
            authorized=True, trusted_worker=True, human_approved=True,
        )
    monkeypatch.setenv("SKL_DRAGON_KNOWLEDGE_DB_PATH", str(db_path))
    monkeypatch.setattr(route.time, "time", lambda: now + 5)
    with TestClient(app) as client:
        result = client.get("/api/dragon-academy/knowledge/hoag")
        assert result.status_code == 200
        assert result.headers["cache-control"] == "private, no-store"
        assert result.json()["items"][0]["mechanic"] == "platforming"
        assert result.json()["items"][0]["training_authorized"] is False
        assert "Jump timing" not in result.text
        assert client.post("/api/dragon-academy/knowledge/hoag", json={}).status_code == 405
        assert client.post("/api/dragon-academy/knowledge/recrawls", json={}).status_code == 405
        app.dependency_overrides[route.get_current_user] = lambda: {
            "email": "bob@example.test", "tenant_id": "tenant-a", "role": "viewer",
        }
        assert client.get("/api/dragon-academy/knowledge/hoag").json()["items"] == []
        app.dependency_overrides[route.get_current_user] = lambda: None
        assert client.get("/api/dragon-academy/knowledge/hoag").status_code == 401
        app.dependency_overrides[route.get_current_user] = lambda: {
            "email": "alice@example.test", "tenant_id": "tenant-a", "role": "viewer",
        }
        with ReviewedKnowledgeStore(db_path) as library:
            DragonWisdomPyramid(library).recrawl(
                owner, "source-a", reason="changed_source",
                expected_revision=revisions["a"].revision_digest,
                now=now + 6, authorized=True, trusted_worker=True,
            )
        monkeypatch.setattr(route.time, "time", lambda: now + 7)
        result = client.get("/api/dragon-academy/knowledge/recrawls")
        assert result.status_code == 200
        assert result.json()["orders"][0]["source_id"] == "source-a"
        assert result.json()["orders"][0]["execution_authorized"] is False
        assert client.get("/api/dragon-academy/knowledge/hoag").json()["items"] == []

def test_guarded_pulse_requires_configured_shared_runtime():
    from starlette.requests import Request
    from fastapi import FastAPI
    app=FastAPI()
    request=Request({'type':'http','app':app})
    with pytest.raises(HTTPException) as exc:
        route.pulse_practice(request,owner=identity())
    assert exc.value.status_code==503


def test_guarded_pulse_runs_native_subscription_and_defers_under_heat(tmp_path,monkeypatch):
    from starlette.requests import Request
    from fastapi import FastAPI
    from dataclasses import replace
    from skeleton.ai.webcrawler.dragon_chunk_executor import DragonChunkExecutor
    from skeleton.ai.webcrawler.dragon_resource_session import DragonResourceSession, HardwareSample
    from skeleton.ai.game_builder.resource_governor import ResourceGovernor, ResourceEnvelope
    from skeleton.kernel.global_resource_scheduler import GlobalResourceScheduler, GlobalResourcePolicy, ResourceVector, PlanePolicy
    app=FastAPI();owner=identity()
    scheduler=GlobalResourceScheduler(GlobalResourcePolicy(ResourceVector(cpu_millis=4000,memory_mb=256,io_tokens=10),
        (PlanePolicy('interactive',2,ResourceVector(),1.),PlanePolicy('background',1,ResourceVector(),1.))))
    hardware=HardwareSample(256*1024**2,4,.1,.9,True,False,10)
    executor=DragonChunkExecutor(DragonResourceSession(global_resources=scheduler,tenant=owner),
        ResourceGovernor(ResourceEnvelope(100,10,1000000,3,1,1,10)),lambda:hardware,clock=lambda:10)
    app.state.dragon_practice_executor_factory=lambda authenticated_owner: executor
    request=Request({'type':'http','app':app})
    path=tmp_path/'pulse.sqlite';monkeypatch.setenv('SKL_DRAGON_PRACTICE_DB_PATH',str(path))
    with route._lab() as (lab,cycles):
        lab.offer(approved(owner),authorized=True,now=10)
        cycles.enable(owner,authorized=True,human_approved=True,now=10,expires_at=3010,
            demos_per_tick=2,max_ticks=2,generation_mode='native')
    executor.hardware=lambda:replace(hardware,thermal_limited=True)
    deferred=route.pulse_practice(request,owner=owner)
    assert deferred['resource_execution']['reason']=='thermal_or_pressure'
    assert deferred['subscription']['remaining_ticks']==2 and not deferred['created']
    executor.hardware=lambda:hardware
    result=route.pulse_practice(request,owner=owner)
    assert len(result['created'])==2 and result['resource_execution']['done']
    assert result['subscription']['remaining_ticks']==1
    assert scheduler.usage('background').empty
    with pytest.raises(HTTPException) as exc:
        route.pulse_practice(request,owner=identity('other@example.test'))
    assert exc.value.status_code==503




def test_signed_custody_and_memory_route_fail_closed_on_rollback(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from skeleton.ai.game_builder.reviewed_knowledge import (
        ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
    )
    from skeleton.ai.game_builder.dragon_wisdom_authority import DragonWisdomAuthority
    from skeleton.ai.game_builder.dragon_wisdom_memory import DragonWisdomMemory
    from skeleton.ai.game_builder.dragon_wisdom_pyramid import DragonWisdomPyramid
    from skeleton.ai.game_builder.dragon_wisdom_custody import DragonCustodyAnchor

    owner = identity()
    now = 1791644400
    db_path = tmp_path / "source-evidence.sqlite"
    anchor_dir = tmp_path / "external-anchors"
    anchor_dir.mkdir()
    monkeypatch.setenv("SKL_DRAGON_KNOWLEDGE_DB_PATH", str(db_path))
    monkeypatch.setenv("SKL_DRAGON_WISDOM_CUSTODY_REQUIRED", "1")
    monkeypatch.setenv("SKL_DRAGON_WISDOM_ANCHOR_DIR", str(anchor_dir))
    monkeypatch.setenv("SKL_DRAGON_WISDOM_ANCHOR_KEY_HEX", "cd"*32)
    monkeypatch.setattr(route.time, "time", lambda: now+3)

    with ReviewedKnowledgeStore(db_path) as library:
        pyramid = DragonWisdomPyramid(library)
        for suffix in ("a", "b"):
            text = "Original input delay measurements and game design."
            library.import_document(ReviewedDocument(
                owner=owner, source_id="source-"+suffix,
                source_url="https://example.org/"+suffix,
                title="Original mechanics study", text=text,
                observed_at="2026-10-10T12:00:00Z",
                license_id="approved-design-reference",
                allowed_scopes=("design_reference",),
                reviewer_id="source-reviewer-"+suffix, approved=True,
                notes=(ReviewedNote(
                    note_id="note-"+suffix, mechanic="platforming",
                    statement="Input timing has measurable constraints.",
                    start=0, end=len("Original input delay"),
                    stance="supports", confidence_ppm=900000,
                    dependence_group="publisher-"+suffix,
                    tags=("input", "delay"),
                ),),
            ), expected_parent_digest=None, authorized=True)
        brief = library.build_brief(
            owner, "input", authorized=True, min_independent_groups=2,
        )
        auth = DragonWisdomAuthority(
            pyramid, wiki_signing_key=b"r"*32,
            approval_signing_key=b"a"*32, issuer="studio-identity",
        )
        wiki_grant = auth.issue_grant(
            owner, "wiki-reviewer", "neutral-lab", "wiki_reviewer",
            brief.to_payload()["brief_digest"], now=now, expires_at=now+60,
            identity_verified=True, authorized=True,
        )
        review = auth.review(
            owner, brief, mechanic="platforming", disposition="accepted",
            review_evidence_digest="e"*64, grant=wiki_grant,
            now=now, expires_at=now+3600,
            authorized=True, trusted_worker=True,
        )
        approve_grant = auth.issue_grant(
            owner, "human-approver", "governance", "memory_approver",
            review["digest"], now=now, expires_at=now+60,
            identity_verified=True, authorized=True,
        )
        auth.approve(
            owner, review["digest"], grant=approve_grant,
            now=now+1, authorized=True, trusted_worker=True,
        )
        DragonWisdomMemory(pyramid).reconcile(
            owner, now=now+2, authorized=True, trusted_worker=True,
        )

    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.get_current_user] = lambda: {
        "email": "alice@example.test", "tenant_id": "tenant-a", "role": "viewer",
    }
    with TestClient(app) as client:
        # Even correctly signed approvals cannot be served without a separate
        # externally anchored journal head when strict custody is configured.
        assert client.get("/api/dragon-academy/knowledge/hoag").status_code == 409
        assert client.get("/api/dragon-academy/knowledge/memory").status_code == 409
        with ReviewedKnowledgeStore(db_path) as library:
            pyramid = DragonWisdomPyramid(library)
            DragonCustodyAnchor(anchor_dir, signing_key=bytes.fromhex("cd"*32)).checkpoint(
                pyramid, owner, now=now+2, authorized=True,
                trusted_worker=True, allow_initial_bootstrap=True,
            )
        response = client.get("/api/dragon-academy/knowledge/memory")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "private, no-store"
        assert len(response.json()["items"]) == 1
        assert response.json()["items"][0]["training_authorized"] is False
        assert client.get("/api/dragon-academy/knowledge/memory?mechanic=other").json()["items"] == []
        assert client.post("/api/dragon-academy/knowledge/memory", json={}).status_code == 405
        app.dependency_overrides[route.get_current_user] = lambda: {
            "email": "bob@example.test", "tenant_id": "tenant-a", "role": "viewer",
        }
        assert client.get("/api/dragon-academy/knowledge/memory").status_code == 409
        app.dependency_overrides[route.get_current_user] = lambda: {
            "email": "alice@example.test", "tenant_id": "tenant-a", "role": "viewer",
        }
        with ReviewedKnowledgeStore(db_path) as library:
            pyramid = DragonWisdomPyramid(library)
            pyramid.revoke(owner, review["digest"], reason="rights_change",
                           now=now+3, authorized=True, trusted_worker=True)
        assert client.get("/api/dragon-academy/knowledge/memory").status_code == 409
        with ReviewedKnowledgeStore(db_path) as library:
            pyramid = DragonWisdomPyramid(library)
            DragonCustodyAnchor(anchor_dir, signing_key=bytes.fromhex("cd"*32)).checkpoint(
                pyramid, owner, now=now+4, authorized=True,
                trusted_worker=True,
            )
        assert client.get("/api/dragon-academy/knowledge/memory").json()["items"] == []
