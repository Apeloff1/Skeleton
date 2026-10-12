"""Canonical custody adapter regression: no user-issued Dragon Family XP."""
from __future__ import annotations

from hashlib import sha256
import sqlite3

import pytest

from skeleton.ai.webcrawler.core import CrawlDocument
from skeleton.ai.webcrawler.dragon_family import SourceReceipt
from skeleton.ai.webcrawler.dragon_family_custody_bridge import (
    ApprovedSourceSnapshot, DragonFamilyCustodyBridge, _canonical,
)
from skeleton.ai.webcrawler.dragon_game_mechanics import Mechanic
from skeleton.ai.webcrawler.dragon_knowledge_ledger import DragonKnowledgeLedger
from skeleton.ai.webcrawler.dragon_knowledge_promotion import PromotionDecision
from skeleton.ai.webcrawler.dragon_practice_lab import ApprovedLesson, DragonPracticeLab
from skeleton.ai.webcrawler.dragon_probabilistic_distillation import EvidencePass
from skeleton.ai.webcrawler.video_digest import VideoKnowledgeChunk


OWNER = "study-owner"
NOW = 1800000000.0
URL = "https://example.org/design/puzzles"


def document(text: str, fetched_at=NOW + 1, url=URL) -> CrawlDocument:
    digest = sha256(text.encode("utf-8")).hexdigest()
    provenance = {
        "schema": "skeleton.ai.crawl.provenance.v1", "canonical_url": url,
        "fetched_url": url, "content_hash": digest,
        "fetched_at": fetched_at, "status": 200,
    }
    return CrawlDocument(url, url, "Design tutorial", text, "text/html",
                         digest, fetched_at, .9, provenance, ())


def grant(db: sqlite3.Connection, *, sid: str, digest: str, claim="claim-one",
          owner=OWNER, review="a" * 64) -> None:
    ledger = DragonKnowledgeLedger(db)
    for index in range(3):
        ledger.add(owner, EvidencePass(
            source_id=sid, source_revision=digest, pass_id=f"pass-{index}",
            claim_id=claim, supports=True, confidence=.99,
            reliability=.99, independence_group="publisher-one",
            evidence_locator=f"sha256:{digest}@0:12",
            observation="locally validated source excerpt",
        ), authorized=True)
    belief = ledger.belief(owner, claim, authorized=True)
    decision = PromotionDecision(
        claim, True, .99, "empirically_calibrated_probability",
        "b" * 64, (), belief.evidence_digest,
    )
    DragonPracticeLab(db).offer(
        ApprovedLesson(owner, "Puzzle design tutorial", decision, review,
                       (Mechanic.MOVEMENT,), True), authorized=True, now=NOW,
    )


def snap(sid: str, media: str = "article", *, at=NOW + 10,
         url=URL, claim="claim-one", improvement="") -> ApprovedSourceSnapshot:
    return ApprovedSourceSnapshot(sid, media, url, ("game_design",),
                                  claim, at, improvement)


def test_article_requires_existing_approved_lesson_and_exact_document_hash():
    db = sqlite3.connect(":memory:")
    bridge = DragonFamilyCustodyBridge(db, OWNER)
    doc = document("A deterministic maze with bounded NPC behavior.")
    with pytest.raises(PermissionError, match="canonical review"):
        bridge.article(snap("web-1"), doc)
    grant(db, sid="web-1", digest=doc.content_hash)
    source, approved = bridge.article(snap("web-1"), doc)
    assert source.url == URL and source.media == "article"
    assert approved.content_digest == doc.content_hash
    assert bridge.verify(approved)
    assert not bridge.verify(SourceReceipt(
        "web-1", doc.content_hash, "f" * 64, NOW + 10))
    assert not DragonFamilyCustodyBridge(db, "another-owner").verify(approved)
    family = bridge.family()
    family.enroll(OWNER, (source,), authorized=True, now=NOW + 2)
    family.seal_inventory(OWNER, authorized=True, now=NOW + 3)
    family.consume(OWNER, approved, authorized=True)
    assert family.snapshot(OWNER, authorized=True)["parent"]["complete"]
    # A display-only bridge without canonical records cannot mint parent XP.
    with pytest.raises(PermissionError):
        bridge.family().consume(OWNER, SourceReceipt(
            "web-1", "e" * 64, "f" * 64, NOW + 20), authorized=True)


def test_article_tampered_capture_and_untrusted_url_are_refused():
    db = sqlite3.connect(":memory:")
    bridge = DragonFamilyCustodyBridge(db, OWNER)
    doc = document("Original verified content")
    grant(db, sid="web-1", digest=doc.content_hash)
    bad = CrawlDocument(
        doc.canonical_url, doc.fetched_url, doc.title, doc.text + " poison",
        doc.content_type, doc.content_hash, doc.fetched_at, doc.source_score,
        doc.provenance, doc.links)
    with pytest.raises(ValueError):
        bridge.article(snap("web-1"), bad)
    with pytest.raises(ValueError):
        bridge.article(snap("web-1", url="https://localhost/stolen"), doc)
    with pytest.raises(ValueError):
        bridge.article(snap("web-1", at=NOW - 10), doc)


def test_revocation_and_stale_evidence_index_block_family_growth():
    db = sqlite3.connect(":memory:")
    bridge = DragonFamilyCustodyBridge(db, OWNER)
    doc = document("Evidence first version")
    grant(db, sid="web-1", digest=doc.content_hash)
    _, proof = bridge.article(snap("web-1"), doc)
    assert bridge.verify(proof)
    # New readings change the canonical evidence set, invalidating older
    # cached promotion until another independently reviewed promotion.
    DragonKnowledgeLedger(db).add(OWNER, EvidencePass(
        "web-1", doc.content_hash, "extra-pass", "claim-one", True, .8, .9,
        "publisher-one", "sha256:" + doc.content_hash + "@0:8", "new detail",
    ), authorized=True)
    assert not bridge.verify(proof)
    # A new review should restore the identity of the revised evidence set.
    belief = DragonKnowledgeLedger(db).belief(OWNER, "claim-one", authorized=True)
    decision = PromotionDecision(
        "claim-one", True, .99, "empirically_calibrated_probability",
        "b" * 64, (), belief.evidence_digest)
    DragonPracticeLab(db).offer(ApprovedLesson(
        OWNER, "Approved second review", decision, "c" * 64, (Mechanic.MOVEMENT,), True,
    ), authorized=True, now=NOW + 20)
    refreshed = bridge.article(snap("web-1", at=NOW + 25), doc)[1]
    assert refreshed.review_digest == "c" * 64
    assert bridge.verify(refreshed)
    DragonPracticeLab(db).revoke(OWNER, authorized=True)
    assert not bridge.verify(refreshed)


def test_video_digest_only_from_approved_timecoded_chunks():
    db = sqlite3.connect(":memory:")
    bridge = DragonFamilyCustodyBridge(db, OWNER)
    clip_url = "https://example.org/watch/puzzle"
    chunk = VideoKnowledgeChunk(
        "c" * 64, 0, 15000, "Explaining original puzzle composition",
        ("transcript",), ("observer-1",), clip_url,
    )
    evidence = [{
        "chunk": chunk.chunk_id, "start": chunk.start_ms,
        "end": chunk.end_ms, "text": chunk.text,
        "modalities": chunk.modalities, "observations": chunk.observation_ids,
    }]
    digest = sha256(_canonical({"source": clip_url, "chunks": evidence})).hexdigest()
    v = snap("vid-1", "video", url=clip_url)
    with pytest.raises(PermissionError):
        bridge.video(v, (chunk,))
    grant(db, sid="vid-1", digest=digest, claim="clip-review")
    source, proof = bridge.video(v, (chunk,))
    assert source.media == "video" and proof.content_digest == digest
    assert bridge.verify(proof)
    bad = VideoKnowledgeChunk(chunk.chunk_id, chunk.start_ms,
                              chunk.end_ms, chunk.text, chunk.modalities,
                              chunk.observation_ids, "https://example.org/mismatch")
    with pytest.raises(ValueError):
        bridge.video(v, (bad,))
    with pytest.raises(ValueError):
        bridge.video(v, ())
