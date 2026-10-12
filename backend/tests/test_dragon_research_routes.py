"""Dragon research dashboard: trusted storage composition and read-only routes."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI, HTTPException, Request, Response

from core.routes_registry import KNOWN_ROUTES
from core.dragon_research_session import DragonResearchSessionFactory
from routes import dragon_research
from routes.dragon_academy import _principal
from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_technical_source_atlas import DragonTechnicalSources
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore

NEST_KEY=b"separately-provisioned-nest-test-secret-32-bytes"
REVIEW_KEY=b"\x21"*32


@pytest.fixture
def storage(tmp_path):
    knowledge=tmp_path/"knowledge.sqlite"
    nest=tmp_path/"nest.sqlite"
    with ReviewedKnowledgeStore(knowledge) as library:
        almanacs=DragonAlmanacs(library)
        atlas=DragonTechnicalSources(almanacs)
        owner=_principal({
            "email":"alice@example.test","tenant_id":"tenant-a","role":"editor"})
        atlas.import_catalog(owner,authorized=True,recorded_at=1791800000)
    with sqlite3.connect(nest) as db:
        DragonNestStore(db,signing_key=NEST_KEY)
    return knowledge,nest,owner


def factory(paths):
    knowledge,nest,_=paths
    return DragonResearchSessionFactory(
        knowledge_path=knowledge,nest_path=nest,
        nest_key=NEST_KEY,
        transcript_review_public_key=REVIEW_KEY,
        transcript_issuer="independent-transcript-reviewer",
        transcript_key_id="ed25519-review-v1",
    )


def request(app):
    return Request({"type":"http","method":"GET","path":"/","app":app})


def test_research_router_is_registered_read_only_and_role_guarded():
    assert ("routes.dragon_research","router") in KNOWN_ROUTES
    methods={
        route.path:route.methods for route in dragon_research.router.routes
    }
    assert set(methods)=={
        "/api/dragon-research/status",
        "/api/dragon-research/sources",
        "/api/dragon-research/mother-review",
    }
    assert all(verbs=={"GET"} for verbs in methods.values())
    protected=next(
        route for route in dragon_research.router.routes
        if route.path.endswith("/mother-review"))
    depnames={d.call.__name__ for d in protected.dependant.dependencies}
    assert "_principal" in depnames
    assert "dep" in depnames  # GameForge require_role("editor")


def test_unmounted_dashboard_returns_503_and_forged_id_is_422():
    app=FastAPI()
    with pytest.raises(HTTPException) as unavailable:
        dragon_research.source_catalog(request(app),Response(),limit=20,
                                       after_source=None,owner="studio")
    assert unavailable.value.status_code==503
    with pytest.raises(HTTPException) as invalid:
        dragon_research._identity("../../etc/passwd","video")
    assert invalid.value.status_code==422
    with pytest.raises(HTTPException) as anonymous:
        _principal({"role":"admin","email":"a@example.test","dev_mode":True})
    assert anonymous.value.status_code==401


def test_factory_keeps_research_tenants_isolated_and_fails_closed(storage):
    app=FastAPI()
    f=factory(storage)
    dragon_research.install_dragon_research_dashboard(app,f)
    with pytest.raises(ValueError,match="already"):
        dragon_research.install_dragon_research_dashboard(app,f)
    _,_,owner=storage
    response=dragon_research.source_catalog(
        request(app),Response(),limit=20,after_source=None,owner=owner)
    assert response["schema"]=="skeleton.dragon.research_source_catalog.v1"
    assert response["read_only"] and response["network_requests"]==0
    assert response["page_size"]<=20 and response["has_more"]
    assert not response["training_authorized"]
    stranger=dragon_research.source_catalog(
        request(app),limit=20,after_source=None,owner="other-tenant")
    assert stranger["entries"]==[]
    with pytest.raises(HTTPException) as missing:
        dragon_research.three_hatchlings_status(
            request(app),Response(),article="source-"+"a"*64,
            video="source-"+"b"*64,updates="source-"+"a"*64,
            owner=owner)
    assert missing.value.status_code==409
    assert all(not row["is_rights_approval"] for row in response["entries"])


def test_configured_factory_must_not_autocreate_missing_sqlite_files(tmp_path):
    with pytest.raises(ValueError,match="existing canonical"):
        DragonResearchSessionFactory(
            knowledge_path=tmp_path/"not-created.sqlite",
            nest_path=tmp_path/"not-created-nest.sqlite",
            nest_key=NEST_KEY,
            transcript_review_public_key=REVIEW_KEY,
            transcript_issuer="separate-reviewer",transcript_key_id="v1")
    assert not (tmp_path/"not-created.sqlite").exists()
    assert not (tmp_path/"not-created-nest.sqlite").exists()


def test_environment_opt_in_missing_requirements_rejected(storage,monkeypatch):
    knowledge,nest,_=storage
    monkeypatch.setenv("SKL_DRAGON_KNOWLEDGE_DB_PATH",str(knowledge))
    monkeypatch.setenv("SKL_DRAGON_PRACTICE_DB_PATH",str(nest))
    monkeypatch.delenv("SKL_DRAGON_TRANSCRIPT_REVIEW_PUBLIC_KEY_HEX",raising=False)
    monkeypatch.setenv("SKL_DRAGON_NEST_SIGNING_KEY_HEX",NEST_KEY.hex())
    monkeypatch.setenv("SKL_DRAGON_TRANSCRIPT_REVIEW_ISSUER","independent-reviewer")
    monkeypatch.setenv("SKL_DRAGON_TRANSCRIPT_REVIEW_KEY_ID","v1")
    with pytest.raises(ValueError,match="public key"):
        DragonResearchSessionFactory.from_env()
    monkeypatch.setenv("SKL_DRAGON_TRANSCRIPT_REVIEW_PUBLIC_KEY_HEX",REVIEW_KEY.hex())
    f=DragonResearchSessionFactory.from_env()
    with f.open() as coordinator:
        assert coordinator.source_catalog("other-tenant",authorized=True)["entries"]==[]
