"""Smoke tests for the deep-cut + build-plan work (2026-08).

Covers the surfaces landed across the cut ledger and build plan that had
never been executed when written:

  - kernel queue: DRR lanes + opt-in deadline expiry / submitter caps (D2)
  - kernel shims: workqueue / fair_queue / vclock resolve to canonicals
  - retrieval: FeatureReranker disambiguation + rank-stage pipeline (C1)
  - memory: prefix renderer byte-determinism + warmer persistence (B2/B3)
  - api: idempotency guard replay semantics (A4)
  - quad: bus event shape fix + genesis wiring (this round)

Run: pytest skeleton/testing/test_build_plan_smoke.py -v
"""

from __future__ import annotations

import time

import pytest


# ── kernel queue (D2 + shim resolution, D1) ──────────────────────────────

def test_work_queue_drr_fair_share():
    from skeleton.kernel.work_queue import WorkQueue

    q = WorkQueue(max_in_flight=10)
    q.add_lane("heavy", weight=3.0)
    q.add_lane("light", weight=1.0)
    for i in range(8):
        q.enqueue("heavy", f"h{i}")
        q.enqueue("light", f"l{i}")
    order = [q.dequeue()[0] for _ in range(4)]
    assert order[0] == "heavy"          # higher weight earns the first turn
    assert "light" in order             # the light lane is not starved


def test_work_queue_deadline_expiry():
    from skeleton.kernel.work_queue import WorkQueue

    q = WorkQueue(max_in_flight=4)
    q.add_lane("lane")
    q.enqueue("lane", "zombie", deadline=time.time() - 1)
    q.enqueue("lane", "alive")
    lane, item = q.dequeue()
    assert item.item_id == "alive"      # expired work retired, never runs
    assert q.stats()["expired"] == 1


def test_work_queue_submitter_cap():
    from skeleton.kernel.work_queue import SubmitterCapError, WorkQueue

    q = WorkQueue(per_submitter_cap=2)
    q.add_lane("lane")
    q.enqueue("lane", "a", submitter="noisy")
    q.enqueue("lane", "b", submitter="noisy")
    with pytest.raises(SubmitterCapError):
        q.enqueue("lane", "c", submitter="noisy")
    q.enqueue("lane", "d", submitter="quiet")  # other submitters unaffected


def test_submitter_cap_error_exported_from_kernel_package():
    from skeleton.kernel import SubmitterCapError
    from skeleton.kernel.work_queue import SubmitterCapError as Direct

    assert SubmitterCapError is Direct


def test_queue_shims_resolve_to_canonical():
    from skeleton.kernel import workqueue as wq_shim
    from skeleton.kernel import fair_queue as fq_shim
    from skeleton.kernel.work_queue import WorkQueue

    assert wq_shim.FairWorkQueue is WorkQueue
    assert fq_shim.FairWorkQueue is WorkQueue
    assert wq_shim.WorkItem is fq_shim.WorkItem


def test_vclock_shim_resolves_to_canonical():
    from skeleton.kernel.clocks import VectorClock as Canonical
    from skeleton.kernel.vclock import VectorClock as Shimmed

    assert Shimmed is Canonical
    # immutability contract of the canonical implementation
    a = Canonical().tick("node")
    b = Canonical()
    assert a is not b and b.get("node") == 0


# ── retrieval (FeatureReranker rename + stage pipeline) ──────────────────

def test_feature_reranker_prefers_covering_doc():
    from skeleton.retrieval.reranker import FeatureReranker, Reranker

    assert Reranker is FeatureReranker  # legacy alias intact
    r = FeatureReranker()
    ranked = r.rerank("vector clock merge", [
        {"id": "off", "text": "banana bread recipe", "score": 0.9},
        {"id": "on", "text": "vector clocks merge on receipt", "score": 0.1},
    ])
    assert ranked[0].item_id == "on"    # coverage beats raw first-pass score
    assert ranked[0].features["coverage"] == 1.0


def test_pipeline_stages_optional_and_ordered():
    from skeleton.retrieval.pipeline import SearchPipeline

    class FakePlanner:
        def plan(self, q):
            return q
        def execute(self, q, top_k=None):
            from skeleton.retrieval.fusion import ScoredResult
            return [
                ScoredResult(item_id="a", score=1.0, source="x", metadata={"preview": "alpha"}),
                ScoredResult(item_id="b", score=0.5, source="y", metadata={"preview": "beta"}),
            ]

    # no stages → planner output straight through (back-compat)
    plain = SearchPipeline(FakePlanner()).search("q")
    assert [r.item_id for r in plain.results] == ["a", "b"]

    # rule-boost stage flips the order
    from skeleton.retrieval.rerank import Reranker, RerankRule
    boost_b = Reranker([RerankRule("b", lambda it: it.item_id == "b", boost=10.0)])
    staged = SearchPipeline(FakePlanner(), rule_reranker=boost_b).search("q")
    assert staged.results[0].item_id == "b"


# ── memory (prefix renderer + warmer persistence, B2/B3/B4b) ─────────────

def test_prefix_renderer_deterministic_and_cached():
    from skeleton.memory.prefix_renderer import PrefixRenderer

    r1, r2 = PrefixRenderer(), PrefixRenderer()
    p1, p2 = r1.jeeves_system_prefix(), r2.jeeves_system_prefix()
    assert p1.text == p2.text           # byte-identical → KV-cache hits
    assert p1.sha == p2.sha
    prompt, meta = r1.compose_prompt(p1, "teach me rust", retrieved=["fn main()"])
    assert prompt.startswith(p1.text)
    assert meta["cached_tokens"] == p1.tokens


def test_filler_store_persists_and_reloads(tmp_path):
    from skeleton.memory.warmer import Filler, FillerStore

    path = tmp_path / "fillers.json"
    store = FillerStore(path=path)
    store.put(Filler(key="k", sha="s", text="t", tokens=10, ttl_s=3300,
                     built_at=1.0, refreshed_at=1.0, refresh_count=1))
    reloaded = FillerStore(path=path)
    f = reloaded.get("k")
    assert f is not None and f.sha == "s" and f.refresh_count == 1


@pytest.mark.asyncio
async def test_warmer_refreshes_due_fillers():
    from skeleton.memory.prefix_renderer import PrefixSegment, build_prefix
    from skeleton.memory.warmer import FillerStore, MemoryWarmer

    store = FillerStore()
    store.register_builder("k", lambda: build_prefix("k", [PrefixSegment("s", "text")]))
    warmer = MemoryWarmer(store)
    warmed = await warmer.warm_all()
    assert warmed == ["k"]
    assert store.get("k") is not None


# ── api (idempotency guard, A4) ──────────────────────────────────────────

def test_idempotency_guard_replays_recorded_response():
    from skeleton.api.idempotency import IDEMPOTENCY_HEADER, IdempotencyGuard

    guard = IdempotencyGuard()
    headers = {IDEMPOTENCY_HEADER: "client-key-1"}
    assert guard.replay(headers) is None
    payload = {"status": "materialised"}
    guard.remember(headers, payload)
    assert guard.replay(headers) == payload
    assert guard.replay({}) is None     # no header → never replays
    assert guard.replay({IDEMPOTENCY_HEADER: "other"}) is None


# ── quad retriever (bus event shape fix + genesis wiring) ────────────────

def test_quad_retriever_emits_valid_events_and_serves_cache():
    """Regression: ingest/retrieve previously raised EventBusError because
    quad.py called bus.publish(str, dict) instead of passing a DomainEvent."""
    from skeleton.kernel.events import EventBus
    from skeleton.retrieval.quad import QuadRetriever

    bus = EventBus()
    seen = []
    bus.subscribe("retrieval.*", lambda e: seen.append(e.topic))

    quad = QuadRetriever(bus=bus)
    quad.ingest_document("doc1", "vector clocks merge on message receipt")
    quad.ingest_fact("vector clock", "orders", "causality")

    results = quad.retrieve("vector clocks")
    assert results                      # RRF fusion produced hits
    assert "retrieval.ingested" in seen
    assert "retrieval.completed" in seen

    # second identical retrieve should come from the CAG answer cache
    cached = quad.retrieve("vector clocks")
    assert cached
    topics = [e.topic for e in bus.replay("retrieval.*")]
    assert "retrieval.cache_hit" in topics


def test_genesis_wires_quad_handle():
    from skeleton.genesis import Genesis

    g = Genesis(seed=42).boot()
    quad = g.get("quad")
    assert quad is not None
    assert "interface" in g.report.phases
    assert "quad" in g.report.wired["interface"]
    assert g.health()["healthy"]
