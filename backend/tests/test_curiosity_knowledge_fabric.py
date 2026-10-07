import asyncio
import json

import pytest

from core.curiosity_engine import CuriosityEngine, CuriosityIntegrityError
from core.knowledge_augmented_jeeves import KnowledgeAugmentedJeeves
from core.knowledge_fabric import EvidenceRef, KnowledgeFabric, KnowledgeIntegrityError


def test_publish_projects_every_record_into_all_four_surfaces(tmp_path):
    fabric = KnowledgeFabric(tmp_path)
    record = fabric.publish(
        subject="retrieval augmented generation",
        title="RAG evidence brief",
        summary="Retrieval augments generation with external context.",
        claims=["Retrieval can ground model output in external evidence."],
        questions=["How should stale sources be handled?"],
        contradictions=["Retrieval quality can dominate generation quality."],
        evidence=[EvidenceRef("paper", "section 2", 0.9)],
        tags=["rag", "retrieval"], confidence=0.88, novelty=0.7,
    )
    stem_suffix = f"--{record.id}.md"
    assert any(path.name.endswith(stem_suffix) for path in (tmp_path / "wiki").iterdir())
    assert any(path.name.endswith(stem_suffix) for path in (tmp_path / "hoag").iterdir())
    assert any(path.name.endswith(stem_suffix) for path in (tmp_path / "newsroom").iterdir())
    assert any(path.name.endswith(stem_suffix) for path in (tmp_path / "orientation-room").iterdir())
    assert fabric.get(record.id) == record
    assert fabric.stats()["surface_count"] == 4


def test_catalog_tampering_fails_closed(tmp_path):
    fabric = KnowledgeFabric(tmp_path)
    fabric.publish(subject="x", title="X", summary="summary")
    envelope = json.loads((tmp_path / "catalog.json").read_text())
    record = next(iter(envelope["records"].values()))
    record["summary"] = "tampered"
    (tmp_path / "catalog.json").write_text(json.dumps(envelope))
    with pytest.raises(KnowledgeIntegrityError, match="checksum"):
        KnowledgeFabric(tmp_path)


def test_search_and_orientation_pack_rank_matching_knowledge(tmp_path):
    fabric = KnowledgeFabric(tmp_path)
    high = fabric.publish(subject="quantum error correction", title="Surface codes", summary="Surface codes protect logical qubits.", claims=["Surface codes use repeated syndrome measurement."], tags=["quantum", "error"], confidence=0.9, novelty=0.7)
    fabric.publish(subject="gardening", title="Tomatoes", summary="Tomatoes need light.", claims=["Tomatoes need sunlight."], confidence=0.9)
    hits = fabric.search("quantum error correction", limit=1)
    assert hits[0].id == high.id
    pack = fabric.orientation_pack("quantum error correction")
    assert high.id in pack["record_ids"]
    assert any("syndrome" in claim for claim in pack["claims"])


def test_prompt_signal_creates_ranked_frontier(tmp_path):
    engine = CuriosityEngine(tmp_path)
    for _ in range(4):
        engine.observe_prompt("Explain quantum error correction and surface code thresholds")
    engine.observe_prompt("How do tomato plants grow")
    ranked = engine.frontier()
    assert ranked[0][0].prompt_count == 4
    assert ranked[0][1] > 0
    inquiry = engine.next_inquiry()
    assert inquiry is not None
    assert "quantum" in inquiry.subject
    assert len(inquiry.questions) >= 4


def test_frontier_tampering_fails_closed(tmp_path):
    engine = CuriosityEngine(tmp_path)
    engine.observe_prompt("distributed consensus raft paxos")
    envelope = json.loads((tmp_path / "frontier.json").read_text())
    topic = next(iter(envelope["topics"].values()))
    topic["research_count"] = 9999
    (tmp_path / "frontier.json").write_text(json.dumps(envelope))
    with pytest.raises(CuriosityIntegrityError, match="checksum"):
        CuriosityEngine(tmp_path)


def test_unsupported_claims_are_confidence_capped(tmp_path):
    engine = CuriosityEngine(tmp_path)
    engine.observe_prompt("dark matter candidates")
    inquiry = engine.next_inquiry()
    assert inquiry is not None
    record = engine.accept_finding(inquiry, {
        "summary": "A speculative synthesis without sources.",
        "claims": ["Candidate X explains everything."],
        "confidence": 0.99,
    })
    assert record.confidence == 0.45


def test_evidence_backed_research_cycle_updates_all_knowledge_surfaces(tmp_path):
    engine = CuriosityEngine(tmp_path)
    engine.observe_prompt("vector databases approximate nearest neighbor indexing")

    async def researcher(inquiry, context):
        assert inquiry.subject
        assert "record_ids" in context
        return {
            "title": "ANN indexing brief",
            "summary": "Approximate nearest-neighbor indexes trade exactness for speed and memory efficiency.",
            "claims": ["ANN indexes can reduce retrieval latency relative to exhaustive search."],
            "questions": ["Which index family best fits high-update workloads?"],
            "evidence": [{"source": "benchmark-suite", "locator": "ann/latency", "confidence": 0.8}],
            "confidence": 0.82,
            "tags": ["ann", "vector-db"],
        }

    result = asyncio.run(engine.run_once(researcher))
    assert result["status"] == "learned"
    assert result["surfaces"] == ("wiki", "hoag", "newsroom", "orientation-room")
    assert engine.stats()["research_cycles"] == 1
    assert engine.fabric.stats()["records"] == 1


def test_jeeves_reason_plan_and_review_feed_prompts_back_to_curiosity(tmp_path):
    engine = CuriosityEngine(tmp_path)
    engine.fabric.publish(
        subject="distributed consensus",
        title="Consensus orientation",
        summary="Consensus protocols coordinate replicated state under failures.",
        claims=["Raft separates leader election from log replication."],
        questions=["What failure model is assumed?"],
        evidence=[EvidenceRef("raft-paper", "design", 0.95)],
        tags=["raft", "consensus"], confidence=0.9,
    )
    jeeves = KnowledgeAugmentedJeeves(engine)
    reason = jeeves.reason({"prompt": "Design a distributed consensus service using Raft"})
    assert reason["knowledge_record_ids"]
    assert reason["epistemic_state"] in {"grounded", "partial"}
    assert len(reason["attestation_sha256"]) == 64
    plan = jeeves.plan({"goal": "Design a distributed consensus service using Raft"})
    assert [phase["id"] for phase in plan["phases"]] == ["orient", "resolve", "decompose", "execute", "verify", "learn"]
    review = jeeves.review({"prompt": "distributed consensus Raft", "candidate": "Raft uses leader election and replicated logs."})
    assert review["verdict"] in {"context_aligned", "needs_review"}
    assert engine.stats()["prompt_signals"] >= 3
