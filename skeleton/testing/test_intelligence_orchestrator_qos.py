from __future__ import annotations

import time

import pytest

from skeleton.intelligence.orchestrator import IntelligenceOrchestrator, ReasoningResult


def result(task, answer: str, confidence: float) -> ReasoningResult:
    return ReasoningResult(
        task_id=task.task_id,
        answer=answer,
        confidence=confidence,
        sources=[f"source:{answer}"],
    )


def test_falls_back_after_handler_failure_and_preserves_provenance() -> None:
    orchestrator = IntelligenceOrchestrator(min_confidence=0.7)

    def broken(task):
        raise RuntimeError("provider unavailable")

    orchestrator.register_handler("primary", broken, priority=10)
    orchestrator.register_handler("fallback", lambda task: result(task, "recovered", 0.91))

    response = orchestrator.reason("recover this")

    assert response["answer"] == "recovered"
    assert response["handler"] == "fallback"
    assert response["attempts"][0]["status"] == "failed"
    assert response["attempts"][0]["error_type"] == "RuntimeError"
    assert response["attempts"][1]["status"] == "accepted"
    assert orchestrator.stats()["fallbacks"] == 1


def test_rejects_low_confidence_and_continues_route() -> None:
    orchestrator = IntelligenceOrchestrator(min_confidence=0.8)
    orchestrator.register_handler("fast", lambda task: result(task, "guess", 0.4), priority=10)
    orchestrator.register_handler("strong", lambda task: result(task, "grounded", 0.93))

    response = orchestrator.reason("answer carefully")

    assert response["answer"] == "grounded"
    assert response["attempts"][0] == {
        "handler": "fast",
        "status": "rejected",
        "confidence": 0.4,
        "required_confidence": 0.8,
    }
    assert orchestrator.stats()["rejected"] == 1


def test_handler_specific_confidence_gate_can_be_stricter() -> None:
    orchestrator = IntelligenceOrchestrator(min_confidence=0.2)
    orchestrator.register_handler(
        "strict",
        lambda task: result(task, "not enough", 0.79),
        priority=10,
        min_confidence=0.9,
    )
    orchestrator.register_handler("backup", lambda task: result(task, "enough", 0.8))

    assert orchestrator.reason("q")["handler"] == "backup"


def test_circuit_breaker_removes_repeatedly_failing_handler() -> None:
    calls = {"broken": 0}

    def broken(task):
        calls["broken"] += 1
        raise RuntimeError("boom")

    orchestrator = IntelligenceOrchestrator()
    orchestrator.register_handler(
        "broken",
        broken,
        priority=10,
        failure_threshold=1,
        cooldown_seconds=60,
    )
    orchestrator.register_handler("healthy", lambda task: result(task, "ok", 0.9))

    assert orchestrator.reason("first")["handler"] == "healthy"
    assert orchestrator.reason("second")["handler"] == "healthy"
    assert calls["broken"] == 1
    assert orchestrator.stats()["handlers"]["broken"]["circuit_open"] is True


def test_best_confidence_mode_arbitrates_across_handlers() -> None:
    orchestrator = IntelligenceOrchestrator(selection_mode="best_confidence")
    orchestrator.register_handler("fast", lambda task: result(task, "fast", 0.61), priority=10)
    orchestrator.register_handler("deep", lambda task: result(task, "deep", 0.94))

    response = orchestrator.reason("compare")

    assert response["answer"] == "deep"
    assert response["handler"] == "deep"
    assert [attempt["status"] for attempt in response["attempts"]] == ["accepted", "accepted"]
    assert orchestrator.stats()["fallbacks"] == 0


def test_max_attempts_bounds_expensive_arbitration() -> None:
    orchestrator = IntelligenceOrchestrator(selection_mode="best_confidence", max_attempts=1)
    orchestrator.register_handler("one", lambda task: result(task, "one", 0.6), priority=10)
    orchestrator.register_handler("two", lambda task: result(task, "two", 0.99))

    response = orchestrator.reason("bounded")

    assert response["answer"] == "one"
    assert len(response["attempts"]) == 1


def test_expired_deadline_stops_before_invoking_handler() -> None:
    called = {"value": False}

    def handler(task):
        called["value"] = True
        return result(task, "late", 1.0)

    orchestrator = IntelligenceOrchestrator()
    orchestrator.register_handler("slow", handler)

    response = orchestrator.reason("deadline", deadline=time.time() - 1)

    assert "error" in response
    assert called["value"] is False
    assert response["attempts"][0]["status"] == "deadline_exceeded"
    assert orchestrator.stats()["deadline_exceeded"] == 1


def test_disabled_handler_is_not_invoked() -> None:
    orchestrator = IntelligenceOrchestrator()
    orchestrator.register_handler(
        "disabled", lambda task: result(task, "bad", 1.0), enabled=False, priority=100
    )
    orchestrator.register_handler("active", lambda task: result(task, "good", 0.8))

    assert orchestrator.reason("q")["handler"] == "active"
    orchestrator.set_handler_enabled("active", False)
    assert "error" in orchestrator.reason("q2")


def test_result_cache_reuses_stable_answer_and_tracks_hit() -> None:
    calls = {"count": 0}

    def counted(task):
        calls["count"] += 1
        return result(task, "cached-answer", 0.9)

    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=30)
    orchestrator.register_handler("cached", counted)

    first = orchestrator.reason("same", {"tenant": "a"})
    second = orchestrator.reason("same", {"tenant": "a"})

    assert first["cached"] is False
    assert second["cached"] is True
    assert second["latency_ms"] == 0.0
    assert calls["count"] == 1
    stats = orchestrator.stats()
    assert stats["cache_hits"] == 1
    assert stats["completed"] == 2


def test_cache_key_separates_context_and_confidence_contract() -> None:
    calls = {"count": 0}

    def counted(task):
        calls["count"] += 1
        return result(task, str(task.context["tenant"]), 0.9)

    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=30)
    orchestrator.register_handler("handler", counted)

    assert orchestrator.reason("q", {"tenant": "a"})["answer"] == "a"
    assert orchestrator.reason("q", {"tenant": "b"})["answer"] == "b"
    assert orchestrator.reason("q", {"tenant": "a"}, min_confidence=0.8)["cached"] is False
    assert calls["count"] == 3


def test_cache_key_separates_max_attempts_contract() -> None:
    orchestrator = IntelligenceOrchestrator(
        selection_mode="best_confidence", result_cache_ttl_seconds=30
    )
    orchestrator.register_handler("one", lambda task: result(task, "one", 0.6), priority=10)
    orchestrator.register_handler("two", lambda task: result(task, "two", 0.99))

    limited = orchestrator.reason("same", max_attempts=1)
    expanded = orchestrator.reason("same", max_attempts=2)

    assert limited["answer"] == "one"
    assert expanded["answer"] == "two"
    assert expanded["cached"] is False


def test_disabling_handler_invalidates_cached_answer() -> None:
    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=30)
    orchestrator.register_handler("only", lambda task: result(task, "old", 0.9))

    assert orchestrator.reason("same")["answer"] == "old"
    assert orchestrator.reason("same")["cached"] is True

    orchestrator.set_handler_enabled("only", False)
    after_disable = orchestrator.reason("same")

    assert "error" in after_disable
    assert after_disable["cached"] is False


def test_replacing_handler_invalidates_cached_answer() -> None:
    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=30)
    orchestrator.register_handler("provider", lambda task: result(task, "old", 0.9))

    assert orchestrator.reason("same")["answer"] == "old"
    assert orchestrator.reason("same")["cached"] is True

    orchestrator.register_handler("provider", lambda task: result(task, "new", 0.95))
    replacement = orchestrator.reason("same")

    assert replacement["answer"] == "new"
    assert replacement["cached"] is False


def test_handler_removed_during_execution_cannot_return_stale_result() -> None:
    orchestrator = IntelligenceOrchestrator()

    def volatile(task):
        orchestrator.unregister_handler("volatile")
        return result(task, "stale", 1.0)

    orchestrator.register_handler("volatile", volatile, priority=100)
    orchestrator.register_handler("fallback", lambda task: result(task, "fresh", 0.8))

    response = orchestrator.reason("race")

    assert response["answer"] == "fresh"
    assert response["handler"] == "fallback"
    assert response["attempts"][0]["status"] == "stale"
    assert orchestrator.stats()["fallbacks"] == 1


def test_invalid_handler_result_is_isolated_as_failure() -> None:
    orchestrator = IntelligenceOrchestrator()
    orchestrator.register_handler("invalid", lambda task: {"answer": "wrong type"}, priority=10)
    orchestrator.register_handler("valid", lambda task: result(task, "ok", 0.9))

    response = orchestrator.reason("q")

    assert response["handler"] == "valid"
    assert response["attempts"][0]["error_type"] == "TypeError"


def test_route_explanation_surfaces_quality_and_health() -> None:
    orchestrator = IntelligenceOrchestrator()
    orchestrator.register_handler("low", lambda task: result(task, "low", 0.5), priority=1)
    orchestrator.register_handler("high", lambda task: result(task, "high", 0.9), priority=5)

    route = orchestrator.explain_route()

    assert [entry["capability"] for entry in route] == ["high", "low"]
    assert route[0]["score"] > route[1]["score"]
    assert "success_rate" in route[0]


def test_registration_validates_resilience_contract() -> None:
    orchestrator = IntelligenceOrchestrator()

    with pytest.raises(ValueError):
        orchestrator.register_handler(
            "bad", lambda task: result(task, "x", 1), min_confidence=2
        )
    with pytest.raises(ValueError):
        orchestrator.register_handler(
            "bad", lambda task: result(task, "x", 1), failure_threshold=0
        )
    with pytest.raises(TypeError):
        orchestrator.register_handler("bad", object())
