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
from skeleton.ai.game_builder.dragon_technical_source_captures import DragonSourceCaptures
from skeleton.ai.game_builder.dragon_source_delta_ledger import DragonSourceDeltaLedger
from skeleton.ai.game_builder.dragon_video_transcript_ledger import DragonVideoTranscriptLedger
from skeleton.ai.webcrawler.dragon_nest_source_feed import DragonNestSourceFeed
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore

NEST_KEY=b"separately-provisioned-nest-test-secret-32-bytes"
REVIEW_KEY=b"\x21"*32


@pytest.fixture
def storage(tmp_path):
    knowledge=tmp_path/"knowledge.sqlite"
    nest=tmp_path/"nest.sqlite"
    # Migration is a trusted operator action, NOT a web GET. Create the
    # complete existing schema before opening the read-only dashboard.
    with sqlite3.connect(nest) as db:
        signed_nest=DragonNestStore(db,signing_key=NEST_KEY)
        with ReviewedKnowledgeStore(knowledge) as library:
            almanacs=DragonAlmanacs(library)
            atlas=DragonTechnicalSources(almanacs)
            owner=_principal({
                "email":"alice@example.test","tenant_id":"tenant-a","role":"editor"})
            atlas.import_catalog(owner,authorized=True,recorded_at=1791800000)
            captures=DragonSourceCaptures(almanacs)
            DragonSourceDeltaLedger(captures)
            feed=DragonNestSourceFeed(almanacs,atlas,signed_nest)
            DragonVideoTranscriptLedger(
                feed,review_public_key=REVIEW_KEY,
                issuer="independent-transcript-reviewer",
                key_id="ed25519-review-v1")
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
        "/api/dragon-research/workboard",
        "/api/dragon-research/task-plan",
        "/api/dragon-research/history",
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
        request(app),Response(),limit=20,after_source=None,owner="other-tenant")
    assert stranger["entries"]==[]
    board=dragon_research.research_workboard(
        request(app),Response(),limit=20,after_source=None,owner=owner)
    assert board["schema"]=="skeleton.dragon.research_workboard.v1"
    assert board["read_only"] and board["workers_started"]==0
    assert board["permissions_granted"]==0 and board["xp_awarded"]==0
    assert board["mission_count"]>=0
    assert all(not m["automatically_executable"] for m in board["missions"])
    foreign=dragon_research.research_workboard(
        request(app),Response(),limit=20,after_source=None,owner="other-tenant")
    assert foreign["missions"]==[]
    mother=dragon_research.game_task_research_plan(
        request(app),Response(),task="gameboy physics",
        max_sources=300,limit=6,owner=owner)
    assert mother["schema"]=="skeleton.dragon.task_research_plan.v1"
    assert mother["read_only"] and mother["workers_started"]==0
    assert mother["permissions_granted"]==0 and mother["xp_awarded"]==0
    assert not mother["training_authorized"]
    assert mother["search_scope_exhausted"]
    assert mother["matched_task_terms"]
    other=dragon_research.game_task_research_plan(
        request(app),Response(),task="gameboy",
        max_sources=30,limit=6,owner="other-tenant")
    assert other["suggestions"]==[]
    with pytest.raises(HTTPException) as invalid_task:
        dragon_research.game_task_research_plan(
            request(app),Response(),task="../secret",
            max_sources=30,limit=6,owner=owner)
    assert invalid_task.value.status_code==422
    with pytest.raises(HTTPException) as missing:
        dragon_research.three_hatchlings_status(
            request(app),Response(),article="source-"+"a"*64,
            video="source-"+"b"*64,updates="source-"+"a"*64,
            owner=owner)
    assert missing.value.status_code==409
    assert all(not row["is_rights_approval"] for row in response["entries"])
    with pytest.raises(HTTPException) as inaccessible_history:
        dragon_research.family_research_history(
            request(app),Response(),article="source-"+"a"*64,
            video="source-"+"b"*64,updates="source-"+"a"*64,
            limit=10,owner=owner)
    assert inaccessible_history.value.status_code==409
    assert all("exact_quote" not in item for item in board["missions"])


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



def test_research_read_session_blocks_write_queries_on_both_databases(storage):
    f=factory(storage)
    knowledge,nest,owner=storage
    with f.open() as coordinator:
        assert coordinator.source_catalog(
            owner,authorized=True,limit=1)["page_size"]<=1
        for db in (coordinator.article.captures.db,coordinator.nest.db):
            assert db.execute("PRAGMA query_only").fetchone()[0]==1
            with pytest.raises(sqlite3.OperationalError,match="readonly"):
                db.execute("CREATE TABLE forbidden_research_mutation(x INTEGER)")
            # A write against an existing table must fail even if no rows
            # match. This checks the SQLite-level read-only authority.
            table = ("game_builder_knowledge"
                     if db is coordinator.article.captures.db else
                     "dragon_nest_state")
            with pytest.raises(sqlite3.OperationalError,match="readonly"):
                db.execute("DELETE FROM "+table+" WHERE 1=0")
    for filename in (knowledge,nest):
        with sqlite3.connect(filename) as db:
            assert db.execute("SELECT name FROM sqlite_master WHERE name='forbidden_research_mutation'").fetchone() is None


def test_read_only_web_session_never_auto_migrates_missing_schema(tmp_path):
    knowledge=tmp_path/"legacy.sqlite"
    nest=tmp_path/"legacy-nest.sqlite"
    with ReviewedKnowledgeStore(knowledge):
        pass
    with sqlite3.connect(nest) as db:
        DragonNestStore(db,signing_key=NEST_KEY)
    f=DragonResearchSessionFactory(
        knowledge_path=knowledge,nest_path=nest,
        nest_key=NEST_KEY,transcript_review_public_key=REVIEW_KEY,
        transcript_issuer="independent-transcript-reviewer",
        transcript_key_id="ed25519-review-v1")
    with pytest.raises(sqlite3.OperationalError,match="readonly"):
        with f.open():
            pytest.fail("incomplete research schema must never be shown")
    with sqlite3.connect(knowledge) as db:
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE name='dragon_almanac_sources'"
        ).fetchone() is None



def test_read_session_pins_snapshot_across_concurrent_source_registry_write(storage):
    knowledge,_,owner=storage
    with factory(storage).open() as reader:
        db=reader.article.captures.db
        old=db.execute(
            "SELECT COUNT(*) FROM dragon_almanac_topics"
        ).fetchone()[0]
        # A real operator/worker may be writing while a GET is in flight.
        # The browser must not see half an evolving source inventory.
        with sqlite3.connect(knowledge,timeout=5) as writer:
            writer.execute(
                "INSERT INTO dragon_almanac_topics VALUES(?,?,?,?)",
                ("separate-tenant","topic-concurrent",None,"[]"))
        current=db.execute(
            "SELECT COUNT(*) FROM dragon_almanac_topics"
        ).fetchone()[0]
        assert current==old
    with factory(storage).open() as next_reader:
        fresh=next_reader.article.captures.db.execute(
            "SELECT COUNT(*) FROM dragon_almanac_topics"
        ).fetchone()[0]
        assert fresh==old+1


def test_reviewed_knowledge_mode_ro_rejects_schema_creation(tmp_path):
    path=tmp_path/"knowledge.sqlite"
    with ReviewedKnowledgeStore(path):
        pass
    with ReviewedKnowledgeStore(path,read_only=True) as readonly:
        assert readonly.db.execute("PRAGMA query_only").fetchone()[0]==1
        with pytest.raises(sqlite3.OperationalError,match="readonly"):
            readonly.db.execute("INSERT INTO game_builder_knowledge DEFAULT VALUES")
    with pytest.raises(ValueError,match="read-only"):
        ReviewedKnowledgeStore(tmp_path/"missing.sqlite",read_only=True)
    assert not (tmp_path/"missing.sqlite").exists()
