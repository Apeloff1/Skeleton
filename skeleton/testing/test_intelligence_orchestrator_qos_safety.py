from __future__ import annotations

import time
from typing import Any

import pytest

from skeleton.intelligence.orchestrator import IntelligenceOrchestrator, ReasoningResult


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def emit(self, topic: str, payload: dict[str, Any]) -> None:
        self.events.append((topic, payload))


def _result(task_id: str, answer: Any, confidence: float) -> ReasoningResult:
    return ReasoningResult(
        task_id=task_id,
        answer=answer,
        confidence=confidence,
        sources=["fixture"],
    )


def test_handler_disable_invalidates_cached_result() -> None:
    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=60.0)
    calls = 0

    def handler(task):
        nonlocal calls
        calls += 1
        return _result(task.task_id, {"version": calls}, 0.9)

    orchestrator.register_handler("primary", handler)
    first = orchestrator.reason("same query")
    assert first["cached"] is False
    assert calls == 1

    orchestrator.set_handler_enabled("primary", False)
    after_disable = orchestrator.reason("same query")

    assert after_disable["cached"] is False
    assert after_disable["error"] == "No eligible reasoning handlers are available"
    assert calls == 1


def test_handler_replacement_invalidates_cached_result() -> None:
    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=60.0)

    def first_handler(task):
        return _result(task.task_id, {"handler": "first"}, 0.9)

    def replacement_handler(task):
        return _result(task.task_id, {"handler": "replacement"}, 0.95)

    orchestrator.register_handler("primary", first_handler)
    assert orchestrator.reason("same query")["answer"] == {"handler": "first"}

    orchestrator.register_handler("primary", replacement_handler)
    replacement = orchestrator.reason("same query")

    assert replacement["cached"] is False
    assert replacement["answer"] == {"handler": "replacement"}


def test_handler_unregister_invalidates_cached_result() -> None:
    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=60.0)
    orchestrator.register_handler(
        "primary", lambda task: _result(task.task_id, "old", 0.9)
    )

    assert orchestrator.reason("same query")["answer"] == "old"
    assert orchestrator.unregister_handler("primary") is True

    after_unregister = orchestrator.reason("same query")
    assert after_unregister["cached"] is False
    assert after_unregister["error"] == "No eligible reasoning handlers are available"


def test_cached_nested_answer_is_defensively_isolated() -> None:
    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=60.0)

    def handler(task):
        return _result(task.task_id, {"nested": ["original"]}, 0.9)

    orchestrator.register_handler("primary", handler)
    first = orchestrator.reason("cache isolation")
    first["answer"]["nested"].append("caller-poison")
    first["sources"].append("caller-poison")

    cached = orchestrator.reason("cache isolation")

    assert cached["cached"] is True
    assert cached["answer"] == {"nested": ["original"]}
    assert cached["sources"] == ["fixture"]


def test_expired_deadline_cannot_be_bypassed_by_cache_hit() -> None:
    calls = 0

    def handler(task):
        nonlocal calls
        calls += 1
        return _result(task.task_id, "cached", 0.9)

    orchestrator = IntelligenceOrchestrator(result_cache_ttl_seconds=60.0)
    orchestrator.register_handler("primary", handler)

    warm = orchestrator.reason("deadline cache")
    assert warm["cached"] is False
    assert calls == 1

    expired = orchestrator.reason("deadline cache", deadline=time.time() - 1.0)
    assert expired["cached"] is False
    assert "error" in expired
    assert calls == 1
    assert orchestrator.stats()["deadline_exceeded"] >= 1


def test_handler_exception_text_is_not_exposed_in_result_stats_or_events() -> None:
    sentinel = "TOKEN-super-secret-signed-url-value"
    bus = _RecordingBus()
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


def test_average_confidence_uses_one_population_for_rejections_and_successes() -> None:
    orchestrator = IntelligenceOrchestrator(min_confidence=0.5)
    confidences = iter((0.2, 0.8))

    def handler(task):
        return _result(task.task_id, "answer", next(confidences))

    orchestrator.register_handler("primary", handler)
    rejected = orchestrator.reason("first")
    accepted = orchestrator.reason("second")

    assert "error" in rejected
    assert accepted["answer"] == "answer"
    telemetry = orchestrator.stats()["handlers"]["primary"]
    assert telemetry["rejected"] == 1
    assert telemetry["successes"] == 1
    assert telemetry["avg_confidence"] == pytest.approx(0.5)
