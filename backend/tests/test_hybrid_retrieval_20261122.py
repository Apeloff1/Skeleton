"""Hybrid BM25 + dense retrieval (RRF) and its MemoryBank integration."""

from __future__ import annotations

import math
from collections.abc import Sequence

import pytest

from core.hybrid_retrieval import (
    Bm25,
    FallbackEmbedder,
    HashingEmbedder,
    HybridIndex,
    cosine,
    rrf_fuse,
)
from core.jeeves_memory import MemoryBank


def test_bm25_prefers_rare_terms_over_common_ones():
    docs = {
        "a": "save game save game save game",
        "b": "save game checkpoint",
        "c": "save game menu",
    }
    scores = Bm25(docs).scores("save checkpoint")
    assert max(scores, key=scores.__getitem__) == "b"
    assert Bm25(docs).scores("unknownterm") == {}
    with pytest.raises(ValueError):
        Bm25(docs, b=1.5)


def test_rrf_matches_the_published_formula():
    fused = rrf_fuse([["x", "y"], ["y", "z"]], k=60)
    assert fused["y"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["x"] == pytest.approx(1 / 61)
    assert fused["z"] == pytest.approx(1 / 62)
    with pytest.raises(ValueError):
        rrf_fuse([["x"]], k=0)


def test_local_embedder_is_deterministic_normalised_and_morphology_aware():
    emb = HashingEmbedder()
    a, b, c = emb.embed(["checkpoint recovery", "checkpoints recovered", "orbital mechanics"])
    assert emb.embed(["checkpoint recovery"])[0] == a
    assert math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-9)
    assert cosine(a, b) > 0.3 > cosine(a, c)


class _Provider:
    name = "provider-x"

    def __init__(self, mode: str = "ok") -> None:
        self.mode = mode

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.mode == "down":
            raise ConnectionError("provider unavailable")
        if self.mode == "nan":
            return [[float("nan")] * 4 for _ in texts]
        if self.mode == "short":
            return [[1.0, 0.0] for _ in texts[:-1]]
        return [[1.0 if "save" in t else 0.0, 1.0 if "combat" in t else 0.0, 0.1, 0.0] for t in texts]


@pytest.mark.parametrize("mode", ["down", "nan", "short"])
def test_provider_failure_degrades_to_local_space(mode: str):
    errors: list[str] = []
    provider = _Provider("ok")
    index = HybridIndex(provider=FallbackEmbedder(provider, on_error=lambda e: errors.append(type(e).__name__)))
    index.upsert("s", "quick save before the boss")
    index.upsert("c", "combat tuning for the boss")
    provider.mode = mode
    hits = index.search("save the game")
    assert hits and hits[0].doc_id == "s"
    assert hits[0].dense_space == "local-hashing-v1"
    assert errors


def test_provider_space_is_used_when_healthy_and_never_mixed():
    index = HybridIndex(provider=FallbackEmbedder(_Provider()))
    index.upsert("s", "quick save before the boss")
    hits = index.search("save")
    assert hits[0].dense_space == "provider-x" and hits[0].dense_rank == 1
    # A document indexed while the provider was down has no provider vector;
    # it is reachable lexically but never compared across spaces.
    down = _Provider("down")
    index2 = HybridIndex(provider=FallbackEmbedder(down))
    index2.upsert("d", "save slot")
    down.mode = "ok"
    hit = index2.search("save slot")[0]
    assert hit.dense_space == "provider-x" and hit.dense_rank is None and hit.lexical_rank == 1


def test_index_remove_filter_and_empty_queries():
    index = HybridIndex()
    index.upsert("1", "platformer jump buffer")
    index.upsert("2", "puzzle pad order")
    assert [h.doc_id for h in index.search("jump")][:1] == ["1"]
    assert all(h.doc_id == "2" for h in index.search("jump", allow=lambda d: d == "2"))
    assert [h.doc_id for h in index.search("pad order", allow=lambda d: d == "2")] == ["2"]
    assert index.remove("1") and not index.remove("1")
    assert all(h.doc_id != "1" for h in index.search("jump"))
    assert index.search("") == [] and index.search("the of") == []
    with pytest.raises(ValueError):
        index.upsert("", "x")


def test_memory_bank_hybrid_recall_finds_morphological_matches_keyword_recall_misses():
    bank = MemoryBank()
    now = 1_000_000.0
    bank.remember("ag", "Player kept falling; added checkpoints before every gap", memory_id="m1", created_at=now)
    bank.remember("ag", "Tuned enemy wave pacing for the arena", memory_id="m2", created_at=now)
    bank.remember("ag", "Shop prices felt too high", memory_id="m3", created_at=now)
    keyword = bank.recall("ag", "checkpoint", now=now)
    assert all(row.overlap == 0.0 for row in keyword)  # exact-token overlap misses the plural
    hybrid = bank.recall_hybrid("ag", "checkpoint", now=now)
    assert hybrid[0].record.memory_id == "m1" and hybrid[0].overlap > 0
    assert hybrid[0].score > hybrid[1].score


def test_memory_bank_hybrid_respects_kind_eviction_and_forget():
    bank = MemoryBank(per_agent_capacity=2)
    bank.remember("ag", "first memory about saving", memory_id="old", created_at=1.0)
    bank.remember("ag", "second memory about combat", memory_id="mid", created_at=2.0)
    bank.remember("ag", "third memory about saving again", memory_id="new", created_at=3.0)
    ids = [row.record.memory_id for row in bank.recall_hybrid("ag", "saving", now=3.0)]
    assert "old" not in ids and ids[0] == "new"
    reflection = bank.remember_reflection("ag", "saving matters to players", ["new"])
    rows = bank.recall_hybrid("ag", "saving", kind="reflection", now=3.0)
    assert [row.record.memory_id for row in rows] == [reflection.memory_id]
    assert bank.forget("ag") == 2
    assert bank.recall_hybrid("ag", "saving") == []
    assert bank.recall_hybrid("ag", "saving", limit=0) == []


def test_memory_bank_hybrid_with_failing_provider_still_answers():
    bank = MemoryBank(embedder=_Provider("down"))
    bank.remember("ag", "autosave every checkpoint", memory_id="a", created_at=1.0)
    bank.remember("ag", "boss phase two timing", memory_id="b", created_at=1.0)
    assert bank.recall_hybrid("ag", "autosave", now=1.0)[0].record.memory_id == "a"
