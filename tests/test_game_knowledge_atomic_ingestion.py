"""Fault injection proves atomic source and derived-index batch ingestion."""
from dataclasses import replace
import sqlite3

import pytest

from skeleton.ai.webcrawler.core import CrawlEngine, CrawlPolicy, FetchResponse, extract_document
from skeleton.ai.webcrawler.game_builder_knowledge_runtime import (
    GameKnowledgeIndexingError, KnowledgeDrivenGameBuilder,
)
from skeleton.ai.webcrawler.game_knowledge_index import GameKnowledgeIndex


def document(name="first", text=None):
    url = f"https://docs.example/{name}"
    body = text or (f"{name} movement jump requires collision. CharacterBody2D uses 60 fps. " * 8)
    return extract_document(FetchResponse(url, 200, {"content-type": "text/plain"},
                                          body.encode(), 100), url)


def counts(index):
    tables = ["sources", "passages", "tags", "api", "parameters", "relations"]
    if index.fts_enabled:
        tables.append("fts")
    return {name: index.db.execute(f"SELECT COUNT(*) FROM game_knowledge_{name}").fetchone()[0]
            for name in tables}


def fail_second_document(index):
    index.db.execute("""CREATE TEMP TRIGGER reject_second BEFORE INSERT ON game_knowledge_sources
      WHEN NEW.canonical_url='https://docs.example/second'
      BEGIN SELECT RAISE(ABORT, 'injected index failure'); END""")


def test_storage_failure_rolls_back_every_projection_and_allows_retry():
    index = GameKnowledgeIndex(sqlite3.connect(":memory:"))
    before = counts(index)
    fail_second_document(index)
    docs = (("first", document()), ("second", document("second")))
    with pytest.raises(sqlite3.IntegrityError):
        index.ingest_documents(docs, engine="godot", authorized=True)
    assert counts(index) == before
    assert not index.search("movement")
    assert not index.db.in_transaction
    index.db.execute("DROP TRIGGER reject_second")
    assert index.ingest_documents(docs, engine="godot", authorized=True) == 2
    indexed = counts(index)
    assert indexed["sources"] == 2
    assert index.ingest_documents(docs, engine="godot", authorized=True) == 2
    assert counts(index) == indexed


def test_failed_revision_batch_keeps_previous_current_evidence_and_fts():
    index = GameKnowledgeIndex(sqlite3.connect(":memory:"))
    old = document(text="Original movement collision guidance with jump buffering. " * 12)
    index.ingest_document("first", old, authorized=True)
    before = counts(index)
    fail_second_document(index)
    with pytest.raises(sqlite3.IntegrityError):
        index.ingest_documents((("first", document()), ("second", document("second"))),
                               authorized=True)
    active = index.db.execute("SELECT content_hash FROM game_knowledge_sources WHERE active=1").fetchall()
    assert active == [(old.content_hash,)]
    assert counts(index) == before
    assert index.search("Original")[0].content_hash == old.content_hash
    assert not index.search("CharacterBody2D")


@pytest.mark.parametrize("batch", [False, True])
def test_ingestion_does_not_commit_unrelated_caller_transaction(batch):
    db = sqlite3.connect(":memory:")
    index = GameKnowledgeIndex(db)
    db.execute("CREATE TABLE caller_work(value TEXT)")
    db.execute("INSERT INTO caller_work VALUES('pending')")
    if batch:
        index.ingest_documents((("first", document()),), authorized=True)
    else:
        index.ingest_document("first", document(), authorized=True)
    assert db.in_transaction
    db.rollback()
    assert not db.execute("SELECT * FROM caller_work").fetchall()
    assert counts(index)["sources"] == 0


def test_failed_batch_preserves_callers_pending_work():
    db = sqlite3.connect(":memory:")
    index = GameKnowledgeIndex(db)
    db.execute("CREATE TABLE caller_work(value TEXT)")
    fail_second_document(index)
    db.execute("INSERT INTO caller_work VALUES('pending')")
    with pytest.raises(sqlite3.IntegrityError):
        index.ingest_documents((("first", document()), ("second", document("second"))),
                               authorized=True)
    assert db.in_transaction
    assert db.execute("SELECT * FROM caller_work").fetchall() == [("pending",)]
    assert counts(index)["sources"] == 0
    db.commit()


def test_overflow_is_bounded_and_never_partially_imported():
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    source = document()
    read = []
    def docs():
        while True:
            read.append(1)
            yield source
    with pytest.raises(ValueError, match="budget exceeded"):
        builder.ingest_captured_documents(docs(), engine="web", authorized=True, max_docs=2)
    assert len(read) == 3
    assert counts(builder.knowledge)["sources"] == 0


def test_invalid_second_digest_cannot_leave_first_document_indexed():
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    forged = replace(document("second"), content_hash="0" * 64)
    with pytest.raises(ValueError, match="digest mismatch"):
        builder.ingest_captured_documents((document(), forged), engine="web", authorized=True)
    assert counts(builder.knowledge)["sources"] == 0


def test_direct_batch_invalid_document_rolls_back_prior_insert():
    index = GameKnowledgeIndex(sqlite3.connect(":memory:"))
    with pytest.raises(TypeError):
        index.ingest_documents((("first", document()), ("second", object())), authorized=True)
    assert counts(index)["sources"] == 0


def test_acquisition_index_failure_retains_complete_batch_for_no_fetch_retry():
    class Fetcher:
        calls = 0
        def fetch(self, url, **kwargs):
            self.calls += 1
            doc = document(url.rsplit("/", 1)[1])
            return FetchResponse(url, 200, {"content-type": "text/plain"}, doc.text.encode(), 100)
    fetcher = Fetcher()
    crawler = CrawlEngine(fetcher, policy=CrawlPolicy(max_depth=0, min_host_delay_seconds=0))
    crawler.install_robots("https://docs.example", "User-agent: *\nAllow: /")
    for name in ("first", "second"):
        crawler.enqueue(f"https://docs.example/{name}")
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    fail_second_document(builder.knowledge)
    with pytest.raises(GameKnowledgeIndexingError) as failure:
        builder.resume_acquisition(crawler, engine="godot", now=100, authorized=True)
    batch = failure.value.batch
    assert len(batch.documents) == 2 and batch.requests == 2
    assert batch.stop_reason == "frontier_empty"
    assert isinstance(failure.value.__cause__, sqlite3.IntegrityError)
    assert counts(builder.knowledge)["sources"] == 0
    builder.knowledge.db.execute("DROP TRIGGER reject_second")
    assert builder.ingest_captured_documents(batch.documents, engine="godot", authorized=True) == 2
    assert fetcher.calls == 2
    assert counts(builder.knowledge)["sources"] == 2


def test_successful_batch_survives_database_reopen(tmp_path):
    path = tmp_path / "knowledge.sqlite"
    db = sqlite3.connect(path)
    index = GameKnowledgeIndex(db)
    index.ingest_documents((("first", document()), ("second", document("second"))), authorized=True)
    expected = counts(index)
    db.close()
    reopened = GameKnowledgeIndex(sqlite3.connect(path))
    assert counts(reopened) == expected
    assert {hit.source_id for hit in reopened.search("movement")} == {"first", "second"}


def test_authorization_is_checked_before_iterating_documents():
    index = GameKnowledgeIndex(sqlite3.connect(":memory:"))
    def docs():
        raise AssertionError("must not consume unauthorized input")
        yield
    with pytest.raises(PermissionError):
        index.ingest_documents(docs(), authorized=False)


@pytest.mark.parametrize("budget", [True, 0, 1001, 1.5])
def test_invalid_budget_is_checked_before_iterating_documents(budget):
    builder = KnowledgeDrivenGameBuilder(sqlite3.connect(":memory:"))
    def docs():
        raise AssertionError("invalid budget must fail before reading input")
        yield
    with pytest.raises(ValueError):
        builder.ingest_captured_documents(docs(), engine="web", authorized=True, max_docs=budget)
