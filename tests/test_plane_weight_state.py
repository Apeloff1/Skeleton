"""Adaptive retrieval feedback must be cache-coherent and restart-safe."""

import copy

import pytest

from skeleton.kernel.errors import RetrievalFeedbackError
from skeleton.retrieval.feedback import record_plane_feedback
from skeleton.retrieval.fusion import ScoredResult
from skeleton.retrieval.plane_weights import PlaneWeightLearner, attach_learner
from skeleton.retrieval.quad import QuadRetriever


class _Plane:
    def __init__(self, plane: str) -> None:
        self.plane = plane
        self.calls = 0

    def query(self, query: str, top_k: int):
        self.calls += 1
        return [
            ScoredResult(
                fragment_id=f"{self.plane}-doc",
                content=query,
                score=1.0,
                plane=self.plane,
                provenance="test",
            )
        ]


def test_feedback_invalidates_cached_fusion_and_changes_ranking() -> None:
    quad = QuadRetriever()
    rag = _Plane("rag")
    kag = _Plane("kag")
    quad.register_plane("rag", rag)
    quad.register_plane("kag", kag)
    attach_learner(quad)

    before = quad.retrieve("adaptive", k=2)
    cached = quad.retrieve("adaptive", k=2)
    assert [item.fragment_id for item in before] == ["rag-doc", "kag-doc"]
    assert [item.fragment_id for item in cached] == ["rag-doc", "kag-doc"]
    assert rag.calls == kag.calls == 1

    generation = quad.stats()["cache_generation"]
    quad.observe(["kag"], all_planes=["rag", "kag"])
    assert quad.stats()["cache_generation"] > generation
    assert quad.stats()["cache_size"] == 0

    after = quad.retrieve("adaptive", k=2)
    assert [item.fragment_id for item in after] == ["kag-doc", "rag-doc"]
    assert rag.calls == kag.calls == 2


def test_attaching_learner_invalidates_results_fused_without_it() -> None:
    quad = QuadRetriever()
    quad.register_plane("rag", _Plane("rag"))
    quad.retrieve("cached")
    assert quad.stats()["cache_size"] == 1
    generation = quad.stats()["cache_generation"]

    attach_learner(quad)

    assert quad.stats()["cache_generation"] > generation
    assert quad.stats()["cache_size"] == 0


def test_weight_state_round_trips_without_learning_amnesia() -> None:
    original = QuadRetriever()
    for _ in range(4):
        original.observe(["kag"], all_planes=["rag", "kag"])
    state = original.export_weight_state()
    assert state is not None

    restored = QuadRetriever()
    stats = restored.restore_weight_state(copy.deepcopy(state))

    assert restored.weights == original.weights
    assert restored.export_weight_state() == state
    assert stats["updates"] == 4


def test_corrupt_weight_checkpoint_fails_closed() -> None:
    learner = PlaneWeightLearner()
    state = learner.snapshot()
    state["arms"]["rag"]["wins"] = 2
    state["arms"]["rag"]["trials"] = 1
    with pytest.raises(ValueError):
        PlaneWeightLearner.from_snapshot(state)

    state = learner.snapshot()
    state["version"] = 999
    with pytest.raises(ValueError):
        PlaneWeightLearner.from_snapshot(state)


def test_feedback_rejects_used_plane_missing_from_considered_set() -> None:
    with pytest.raises(RetrievalFeedbackError) as exc:
        record_plane_feedback(
            QuadRetriever(),
            ["rag", "kag"],
            all_planes=["rag"],
        )
    assert exc.value.code == "RET.FEEDBACK"
    assert exc.value.context["missing"] == ["kag"]
