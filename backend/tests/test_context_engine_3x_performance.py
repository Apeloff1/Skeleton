from __future__ import annotations

from collections import deque

import pytest

from knowledge_nexus.engines.context_engine_3x import ContextEngine3x


def _contents(items):
    return [item.content for item in items]


def test_bounded_context_uses_constant_time_deques_and_keeps_running_average() -> None:
    engine = ContextEngine3x(buffer_size=3)

    engine.add_context("one", "test", importance=1.0)
    engine.add_context("two", "test", importance=2.0)
    engine.add_context("three", "test", importance=3.0)
    engine.add_context("four", "test", importance=4.0)

    assert isinstance(engine.active_context, deque)
    assert isinstance(engine.redundant_memory, deque)
    assert engine.active_context.maxlen == 3
    assert engine.redundant_memory.maxlen == 3
    assert _contents(engine.active_context) == ["two", "three", "four"]
    assert _contents(engine.redundant_memory) == ["two", "three", "four"]
    assert engine.meta_context["context_length"] == 3
    assert engine.meta_context["average_importance"] == pytest.approx(3.0)


def test_clear_noise_keeps_redundant_memory_and_meta_context_synchronized() -> None:
    engine = ContextEngine3x(buffer_size=5)
    engine.add_context("filler", "test", importance=1.0)
    engine.add_context("clean signal", "test", importance=3.0)

    engine.noise_filter_threshold = 0.2
    engine.clear_noise()

    assert _contents(engine.active_context) == ["clean signal"]
    assert _contents(engine.redundant_memory) == ["clean signal"]
    assert engine.meta_context["context_length"] == 1
    assert engine.meta_context["average_importance"] == pytest.approx(3.0)


def test_get_active_context_reads_only_the_newest_ten_in_order() -> None:
    engine = ContextEngine3x(buffer_size=20)
    for index in range(15):
        engine.add_context(f"context-{index}", "test")

    snapshot = engine.get_active_context(include_meta=True)

    assert snapshot["active_context"] == [f"context-{index}" for index in range(5, 15)]
    assert snapshot["redundant_memory_size"] == 15
    assert snapshot["meta_context"]["context_length"] == 15


def test_noise_at_threshold_survives_explicit_cleanup() -> None:
    engine = ContextEngine3x(buffer_size=5)
    engine.noise_filter_threshold = 0.25
    engine.add_context("filler", "test", importance=2.0)

    engine.clear_noise()

    assert _contents(engine.active_context) == ["filler"]
    assert _contents(engine.redundant_memory) == ["filler"]
    assert engine.meta_context["average_importance"] == pytest.approx(2.0)
