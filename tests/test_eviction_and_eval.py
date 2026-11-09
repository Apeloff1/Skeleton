"""Cache eviction and eval baselines fail closed."""

import tempfile
from pathlib import Path

import pytest

from skeleton.intelligence.eval_framework import EvalError, EvalSuite
from skeleton.intelligence.quests import QuestObjective, QuestProgress, QuestTemplate, rank_quest_candidates
from skeleton.memory.eviction import EvictionError, evict_for_capacity
from skeleton.memory.warmer import Filler, FillerStore


def _filler(key: str, tokens: int, refreshed_at: float) -> Filler:
    return Filler(
        key=key,
        sha="abc",
        text=key,
        tokens=tokens,
        ttl_s=100,
        built_at=refreshed_at,
        refreshed_at=refreshed_at,
    )


def test_eviction_keeps_the_expensive_prefix_and_rejects_a_bad_capacity() -> None:
    store = FillerStore()
    store.put(_filler("cheap", 10, refreshed_at=0))
    store.put(_filler("hot", 40_000, refreshed_at=1_000))
    evicted = evict_for_capacity(store, capacity=1, now=1_000, hit_counts={"hot": 50, "cheap": 0})
    assert evicted == ["cheap"]
    assert store.get("hot") is not None
    assert store.get("cheap") is None
    with pytest.raises(EvictionError):
        evict_for_capacity(store, capacity=-1)
    assert evict_for_capacity(FillerStore(), capacity=0) == []


def test_eval_does_not_hide_errors_or_downgrade_a_baseline() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        with pytest.raises(EvalError):
            EvalSuite("../escape", root=root)
        suite = EvalSuite("grounding", root=root)
        suite.case("holds", {"x": 1}, lambda output: output["x"] > 0)
        report = suite.run(lambda payload: payload)
        assert report["pass_rate"] == 1.0
        suite.save_baseline(report)
        failing = EvalSuite("grounding", root=root)
        failing.case("holds", {"x": 1}, lambda output: output > 0)
        bad = failing.run(lambda payload: -1)
        failing.save_baseline(bad)
        assert "holds" in bad["regressions"]
        again = failing.run(lambda payload: -1)
        assert "holds" in again["regressions"]

        broken = EvalSuite("errors", root=root)
        broken.case("boom", {"x": 1}, lambda output: True)
        failed = broken.run(lambda payload: (_ for _ in ()).throw(RuntimeError("secret-trace")))
        assert failed["results"][0]["passed"] is False
        assert failed["results"][0]["error"] == "RuntimeError"
        assert "secret-trace" not in str(failed)
        typed = EvalSuite("types", root=root)
        typed.case("n", {}, lambda output: 1)
        with pytest.raises(EvalError):
            typed.run(lambda payload: payload)


def test_existing_eval_rates_and_quest_limit() -> None:
    suite = EvalSuite("basic")
    suite.case("c1", {"x": 1}, lambda out: out > 0)
    suite.case("c2", {"x": -1}, lambda out: out > 0)
    report = suite.run(lambda inp: inp["x"])
    assert report["pass_rate"] == 0.5
    empty = EvalSuite("empty")
    empty.case("nightly", {"x": 1}, lambda output: True, tags=["nightly"])
    assert empty.run(lambda payload: payload, tags=["smoke"])["pass_rate"] == 0.0
    intro = QuestTemplate("intro", "main_story", (QuestObjective("catch", "fish", 1),))
    progress = QuestProgress()
    assert rank_quest_candidates((intro,), progress, max_results=0) == ()
    with pytest.raises(ValueError):
        rank_quest_candidates((intro,), progress, max_results=-1)
