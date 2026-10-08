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
