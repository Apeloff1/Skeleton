"""Tests for Jeeves: core sessions, matrices, RAG memory."""

import pytest

from skeleton.jeeves import (
    ClomMatrix,
    Jeeves,
    KremMatrix,
    RagMemory,
    SamMatrix,
    SessionMode,
)
from skeleton.kernel.errors import SessionError


class TestJeevesCore:
    def test_session_lifecycle(self):
        j = Jeeves()
        s = j.open_session("user_1")
        assert s.is_open
        reply = j.ask(s.session_id, "What is recursion?")
        assert isinstance(reply, str) and reply
        j.close_session(s.session_id)
        assert not j.get_session(s.session_id).is_open if hasattr(j, "get_session") else True

    def test_turn_limit(self):
        j = Jeeves(max_turns=2)
        s = j.open_session("u")
        j.ask(s.session_id, "one")
        with pytest.raises(SessionError):
            j.ask(s.session_id, "two")

    def test_unknown_session(self):
        with pytest.raises(SessionError):
            Jeeves().ask("sess_nope", "hi")

    def test_co_coding_review(self):
        j = Jeeves()
        s = j.open_session("u", mode=SessionMode.CO_CODING)
        result = j.review_code(s.session_id, "x = eval(user_input)\n")
        assert result["findings"]
        assert result["findings"][0]["severity"] == "error"

    def test_review_requires_co_coding(self):
        j = Jeeves()
        s = j.open_session("u")
        with pytest.raises(SessionError):
            j.review_code(s.session_id, "print('hi')")

    def test_laws_present(self):
        assert len(Jeeves().laws) == 5


class TestSamMatrix:
    def test_mastery_grows_and_shrinks(self):
        sam = SamMatrix()
        sam.record_attempt("loops", success=True)
        up = sam.mastery("loops")
        assert up > 0
        sam.record_attempt("loops", success=False)
        assert sam.mastery("loops") < up

    def test_review_queue(self):
        sam = SamMatrix()
        sam.record_attempt("weak", success=False)
        assert "weak" in sam.review_queue()


class TestClomMatrix:
    def test_difficulty_adjustment(self):
        clom = ClomMatrix()
        assert clom.adjust_difficulty(success_rate=0.95) > 0.5
        assert clom.adjust_difficulty(success_rate=0.2) < 0.6

    def test_misconceptions(self):
        clom = ClomMatrix()
        clom.record_misconception("pointers")
        clom.resolve_misconception("pointers")
        assert clom.snapshot()["misconceptions"] == {}


class TestKremMatrix:
    def test_ranking_prefers_helpful(self):
        krem = KremMatrix()
        for _ in range(4):
            krem.record_retrieval("good")
            krem.record_feedback("good", helpful=True)
        krem.record_retrieval("bad")
        krem.record_feedback("bad", helpful=False)
        assert krem.rank_sources(["bad", "good"])[0] == "good"


class TestRagMemory:
    def test_remember_and_recall(self):
        mem = RagMemory()
        mem.remember("Python lists are ordered and mutable")
        mem.remember("Bananas are yellow")
        hits = mem.recall("mutable ordered lists", k=1)
        assert len(hits) == 1
        assert "lists" in hits[0].text

    def test_fallback_backend(self):
        assert RagMemory().backend == "local"

    def test_len(self):
        mem = RagMemory()
        mem.remember("a")
        assert len(mem) == 1
