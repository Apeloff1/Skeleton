"""Tests for Jeeves: core sessions, matrices, RAG memory."""

try:
    import pytest
except ImportError:  # pragma: no cover
    class pytest:  # type: ignore
        class raises:
            def __init__(self, exc):
                self.exc = exc
            def __enter__(self):
                return self
            def __exit__(self, t, v, tb):
                if t is None:
                    raise AssertionError("did not raise")
                return issubclass(t, self.exc)


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
        assert not j.get_session(s.session_id).is_open

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


class TestTactical:
    def test_heat_critical(self):
        from skeleton.jeeves.tactical import TacticalBrain
        b = TacticalBrain("soulslike")
        top = b.recommend_next({"heat": 90, "max_heat": 100, "alive": True, "has_weapon": True})
        assert top.priority == 3
        assert top.axis == "heat"

    def test_bind_via_jeeves(self):
        j = Jeeves()
        s = j.open_session("op", mode=SessionMode.TACTICAL)
        pack = j.bind_era("boomer_shooter")
        assert pack["era"] == "boomer_shooter"
        out = j.advise(s.session_id, {"heat": 10, "has_weapon": False, "alive": True})
        assert out["next"]["axis"] == "forge"
        assert j.get_session(s.session_id).is_open

    def test_ask_tactical_uses_brain(self):
        j = Jeeves()
        s = j.open_session("op", mode=SessionMode.TACTICAL)
        j.bind_era("extraction_now")
        reply = j.ask(s.session_id, "status", context={"telemetry": {"heat": 99, "alive": True, "has_weapon": True}})
        assert "Heat critical" in reply or "critical" in reply.lower()


class TestBuilder:
    def test_deterministic_and_armed_boomer(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        pack = compile_era("boomer_shooter")
        a = BuilderBrain().plan(pack)
        b = BuilderBrain().plan(pack)
        assert a.seed == b.seed
        assert a.spawn_weapon is True  # tempo 0.95
        assert a.room_bias == "combat"
        assert a.enemy_mix["trash"] >= 2

    def test_horror_scavenges(self):
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        pack = compile_era("horror_survival")
        p = BuilderBrain().plan(pack)
        assert p.spawn_weapon is False
        assert p.extract_late is True
        assert p.room_bias in {"heat", "combat", "loot", "balanced"}

    def test_jeeves_plan_build(self):
        j = Jeeves()
        d = j.plan_build()
        assert d["seed"]
        assert d["briefing"]
        assert j.last_plan is not None

    def test_trained_cortex_authors_briefing(self):
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.port import SLOTS
        from skeleton.forge.eras import compile_era
        from skeleton.jeeves.builder import BuilderBrain
        neo = JeevesCortex()
        stim = "plan soulslike forge mix bias ttk extract"
        neo.transformer.fit([stim] * 4)
        neo.think(stim)
        for s in SLOTS:
            neo.acquire(s)
            neo.surpass(s)
        pack = compile_era("soulslike")
        p0 = BuilderBrain().plan(pack)
        p1 = BuilderBrain().plan(pack, cortex=neo)
        assert "LM:" in p1.briefing
        assert any("lm=own" in n for n in p1.notes)
        assert len(p1.briefing) > len(p0.briefing)
        assert "LM:" not in p0.briefing

    def test_status_exposes_organs(self):
        from skeleton.cortex import JeevesCortex
        st = JeevesCortex().status()
        assert "moe" in st and "callosum" in st and "sleep" in st and "rl" in st
        assert st["moe"]["experts"]["left"]["head_kind"] == "numeric"
        assert st["moe"]["experts"]["right"]["head_kind"] == "bias"


class TestIntelligenceOrchestratorQoSSafety:
    @staticmethod
    def _result(task, answer, confidence):
        from skeleton.intelligence.orchestrator import ReasoningResult

        return ReasoningResult(
            task_id=task.task_id,
            answer=answer,
            confidence=confidence,
            sources=["fixture"],
        )

    def test_handler_disable_invalidates_cached_result(self):
        from skeleton.intelligence.orchestrator import IntelligenceOrchestrator

        orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=60.0)
        calls = {"count": 0}

        def handler(task):
            calls["count"] += 1
            return self._result(task, {"version": calls["count"]}, 0.9)

        orchestrator.register_handler("primary", handler)
        first = orchestrator.reason("same query")
        assert first["cached"] is False
        assert calls["count"] == 1

        orchestrator.set_handler_enabled("primary", False)
        after_disable = orchestrator.reason("same query")

        assert after_disable["cached"] is False
        assert after_disable["error"] == "No eligible reasoning handlers are available"
        assert calls["count"] == 1

    def test_handler_replacement_invalidates_cached_result(self):
        from skeleton.intelligence.orchestrator import IntelligenceOrchestrator

        orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=60.0)

        def first_handler(task):
            return self._result(task, {"handler": "first"}, 0.9)

        def replacement_handler(task):
            return self._result(task, {"handler": "replacement"}, 0.95)

        orchestrator.register_handler("primary", first_handler)
        assert orchestrator.reason("same query")["answer"] == {"handler": "first"}

        orchestrator.register_handler("primary", replacement_handler)
        replacement = orchestrator.reason("same query")

        assert replacement["cached"] is False
        assert replacement["answer"] == {"handler": "replacement"}

    def test_cached_nested_answer_is_defensively_isolated(self):
        from skeleton.intelligence.orchestrator import IntelligenceOrchestrator

        orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=60.0)

        def handler(task):
            return self._result(task, {"nested": ["original"]}, 0.9)

        orchestrator.register_handler("primary", handler)
        first = orchestrator.reason("cache isolation")
        first["answer"]["nested"].append("caller-poison")
        first["sources"].append("caller-poison")

        cached = orchestrator.reason("cache isolation")

        assert cached["cached"] is True
        assert cached["answer"] == {"nested": ["original"]}
        assert cached["sources"] == ["fixture"]

    def test_handler_exception_text_is_not_exposed(self):
        from skeleton.intelligence.orchestrator import IntelligenceOrchestrator

        sentinel = "TOKEN-super-secret-signed-url-value"

        class RecordingBus:
            def __init__(self):
                self.events = []

            def emit(self, topic, payload):
                self.events.append((topic, payload))

        bus = RecordingBus()
        orchestrator = IntelligenceOrchestrator(bus=bus)

        def handler(task):
            raise RuntimeError(f"provider failed with {sentinel}")

        orchestrator.register_handler("primary", handler)
        result = orchestrator.reason("redaction")

        assert sentinel not in repr(result)
        assert sentinel not in repr(orchestrator.stats())
        assert sentinel not in repr(bus.events)
        assert result["attempts"] == [
            {
                "handler": "primary",
                "status": "failed",
                "error_type": "RuntimeError",
            }
        ]
        assert orchestrator.stats()["handlers"]["primary"]["last_error"] == "RuntimeError"

    def test_average_confidence_uses_consistent_population(self):
        from skeleton.intelligence.orchestrator import IntelligenceOrchestrator

        orchestrator = IntelligenceOrchestrator(min_confidence=0.5)
        confidences = iter((0.2, 0.8))

        def handler(task):
            return self._result(task, "answer", next(confidences))

        orchestrator.register_handler("primary", handler)
        rejected = orchestrator.reason("first")
        accepted = orchestrator.reason("second")

        assert "error" in rejected
        assert accepted["answer"] == "answer"
        telemetry = orchestrator.stats()["handlers"]["primary"]
        assert telemetry["rejected"] == 1
        assert telemetry["successes"] == 1
        assert abs(telemetry["avg_confidence"] - 0.5) < 1e-9
