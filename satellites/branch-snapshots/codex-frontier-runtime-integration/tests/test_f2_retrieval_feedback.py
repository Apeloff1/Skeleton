"""F-2: plane-feedback → observe() (isolated from FastAPI app boot).

App-level TestClient coverage is blocked on main by the known
PipelineVerifier ↔ cortex.deck circular import (tracked on PR #7).
These tests cover the learner loop and the feedback helper the route calls.
"""

from __future__ import annotations

import pytest

from skeleton.kernel.errors import RetrievalFeedbackError
from skeleton.retrieval.feedback import record_plane_feedback
from skeleton.retrieval.plane_weights import PLANES, attach_learner
from skeleton.retrieval.quad import QuadRetriever


def test_record_plane_feedback_trains_learner():
    quad = QuadRetriever()
    before = dict(quad.weights)
    body = record_plane_feedback(quad, ["rag", "kag"])
    assert body["status"] == "ok"
    assert body["learner"]["updates"] >= 1
    assert body["learner"]["weights"]["rag"] >= body["learner"]["weights"]["mag"]
    assert quad.weights["rag"] >= before["rag"]


def test_record_plane_feedback_rejects_empty():
    with pytest.raises(RetrievalFeedbackError) as ei:
        record_plane_feedback(QuadRetriever(), [])
    assert ei.value.code == "RET.FEEDBACK"


def test_record_plane_feedback_rejects_unknown_plane():
    with pytest.raises(RetrievalFeedbackError) as ei:
        record_plane_feedback(QuadRetriever(), ["nope"])
    assert ei.value.code == "RET.FEEDBACK"
    assert "nope" in ei.value.message


def test_quad_observe_updates_weights_via_learner():
    quad = QuadRetriever()
    attach_learner(quad)
    before = dict(quad.weights)
    stats = quad.observe(["rag", "kag"])
    assert stats["updates"] >= 1
    assert quad.weights["rag"] >= before["rag"]
    assert quad.weights["rag"] >= quad.weights["mag"]
    assert getattr(quad, "_weight_learner").effective_weights()["rag"] == quad.weights["rag"]


def test_retrieve_uses_learner_weights_when_attached():
    quad = QuadRetriever()
    attach_learner(quad)
    for _ in range(8):
        quad.observe(["rag"])
    hits = quad.retrieve("hello world", k=3, use_cache=False)
    assert isinstance(hits, list)
    assert set(quad.stats()["learner"]["weights"]) == set(PLANES)
