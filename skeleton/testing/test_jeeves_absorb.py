from __future__ import annotations

import time

from skeleton.jeeves.absorb import (
    AbsorbEngine,
    AbsorbLane,
    AbsorbSignals,
    AdaptiveRouter,
    Observation,
    Provenance,
    SnapshotEntry,
    SnapshotStore,
    Verification,
)
from skeleton.jeeves.absorb_rag import SnapshotRagSink
from skeleton.jeeves.absorb_runtime import AbsorbRuntime, BackpressurePolicy
from skeleton.jeeves.rag import RagMemory


def _observation(identifier: str, content: str, *, trust: float = 0.95) -> Observation:
    return Observation(
        observation_id=identifier,
        content=content,
        provenance=Provenance(
            source_id="unit-source",
            source_type="test",
            observed_at=time.time(),
            trust=trust,
            evidence=("unit-evidence",),
        ),
    )


def test_submit_is_orthogonal_to_promotion() -> None:
    engine = AbsorbEngine()

    offset = engine.submit(_observation("obs-1", "Novel verified knowledge"))

    assert offset == 0
    assert engine.backlog == 1
    assert engine.current_snapshot() is None

    snapshot = engine.process()

    assert snapshot is not None
    assert snapshot.version == 1
    assert [entry.observation_id for entry in snapshot.entries] == ["obs-1"]
    assert engine.metrics.promoted == 1
    assert engine.metrics.knowledge_gain_per_compute > 0


def test_low_confidence_is_deferred_not_served() -> None:
    engine = AbsorbEngine()
    engine.submit(_observation("weak", "Weakly supported claim", trust=0.30))

    assert engine.process() is None
    assert engine.current_snapshot() is None
    assert engine.metrics.deferred == 1


def test_high_impact_knowledge_requires_challenge_pass() -> None:
    def signals(observation: Observation, duplicate_similarity: float) -> AbsorbSignals:
        return AbsorbSignals(
            novelty=1.0 - duplicate_similarity,
            relevance=1.0,
            information_gain=1.0,
            evidence_quality=1.0,
            urgency=observation.urgency,
            downstream_utility=0.95,
            estimated_compute_cost=1.0,
        )

    blocked = AbsorbEngine(
        signal_estimator=signals,
        verifier=lambda _observation, _signals: Verification(
            confidence=0.99,
            challenge_passed=False,
        ),
    )
    blocked.submit(_observation("impact-blocked", "High impact claim"))
    assert blocked.process() is None
    assert blocked.metrics.challenge_routed == 1
    assert blocked.metrics.deferred == 1

    accepted = AbsorbEngine(
        signal_estimator=signals,
        verifier=lambda _observation, _signals: Verification(
            confidence=0.99,
            challenge_passed=True,
        ),
    )
    accepted.submit(_observation("impact-ok", "High impact checked claim"))
    assert accepted.process() is not None
    assert accepted.metrics.promoted == 1


def test_router_escalates_uncertain_work_to_challenge_lane() -> None:
    router = AdaptiveRouter()
    signals = AbsorbSignals(
        novelty=0.7,
        relevance=0.7,
        information_gain=0.7,
        evidence_quality=0.5,
        urgency=0.1,
        downstream_utility=0.5,
    )

    lanes = router.lanes(signals, Verification(confidence=0.55))

    assert AbsorbLane.FAST in lanes
    assert AbsorbLane.DEEP in lanes
    assert AbsorbLane.CHALLENGE in lanes


def test_integrity_risk_is_quarantined() -> None:
    engine = AbsorbEngine(
        verifier=lambda _observation, _signals: Verification(
            confidence=0.99,
            integrity_risk=0.9,
            challenge_passed=True,
        )
    )
    engine.submit(_observation("risk", "Untrusted mutation attempt"))

    assert engine.process() is None
    assert engine.metrics.quarantined == 1


def test_snapshot_store_can_roll_back_atomically() -> None:
    store = SnapshotStore()
    first = store.publish(
        [SnapshotEntry("a", "fp-a", "alpha", "L2", 0.9, "s", 0)]
    )
    second = store.publish(
        [SnapshotEntry("b", "fp-b", "beta", "L2", 0.9, "s", 1)]
    )

    assert second.version == 2
    assert len(second.entries) == 2
    rolled_back = store.rollback(first.version)
    assert rolled_back == first
    assert store.current == first


def test_rag_receives_only_promoted_snapshot_entries() -> None:
    memory = RagMemory()
    engine = AbsorbEngine(sink=SnapshotRagSink(memory))
    engine.submit(_observation("served", "Promoted retrieval knowledge"))

    assert len(memory) == 0
    snapshot = engine.process()

    assert snapshot is not None
    assert len(memory) == 1
    hit = memory.recall("retrieval knowledge", k=1)[0]
    assert hit.metadata["absorb_snapshot"] == snapshot.version
    assert hit.metadata["observation_id"] == "served"


def test_runtime_yields_capacity_under_serving_pressure() -> None:
    engine = AbsorbEngine()
    for index in range(3):
        engine.submit(_observation(f"obs-{index}", f"Distinct knowledge item {index}"))

    runtime = AbsorbRuntime(
        engine,
        pressure_probe=lambda: 0.95,
        policy=BackpressurePolicy(min_batch=1, normal_batch=2, burst_batch=4, high_backlog=3),
    )

    assert runtime.batch_budget() == 1
    runtime.run_once()
    assert engine.backlog == 2


def test_compute_normalization_prefers_higher_gain_per_cost() -> None:
    def signals(observation: Observation, duplicate_similarity: float) -> AbsorbSignals:
        high = observation.observation_id == "efficient"
        return AbsorbSignals(
            novelty=1.0 - duplicate_similarity,
            relevance=0.9,
            information_gain=0.95 if high else 0.8,
            evidence_quality=0.95,
            urgency=0.2,
            downstream_utility=0.5,
            estimated_compute_cost=0.5 if high else 5.0,
        )

    engine = AbsorbEngine(signal_estimator=signals)
    engine.submit(_observation("expensive", "Expensive useful knowledge"))
    engine.submit(_observation("efficient", "Efficient useful knowledge"))

    first = engine.process(max_items=1)

    assert first is not None
    assert first.entries[0].observation_id == "efficient"
    assert engine.backlog == 1
