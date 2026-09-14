import time

from core.curiosity_engine import CuriosityEngine
from core.idle_curiosity_runtime import IdleCuriosityRuntime


def _researcher(inquiry, context):
    return {
        "summary": f"Evidence-backed notes for {inquiry.subject}.",
        "claims": [f"A grounded claim about {inquiry.subject}."],
        "evidence": [{"source": "test-source", "locator": inquiry.id, "confidence": 0.8}],
        "questions": [f"What remains uncertain about {inquiry.subject}?"],
        "confidence": 0.8,
    }


def test_recent_activity_blocks_idle_cycle(tmp_path):
    engine = CuriosityEngine(tmp_path / "engine")
    runtime = IdleCuriosityRuntime(engine, _researcher, idle_threshold_seconds=60, poll_seconds=0.01)
    runtime.mark_activity("graph neural networks message passing")
    assert runtime.eligible() is False
    snap = runtime.snapshot()
    assert snap["cycles_this_window"] == 0
    assert snap["idle_threshold_seconds"] == 60


def test_manual_cycle_learns_and_updates_counters(tmp_path):
    engine = CuriosityEngine(tmp_path / "engine")
    engine.observe_prompt("compiler intermediate representation SSA optimization")
    runtime = IdleCuriosityRuntime(engine, _researcher, idle_threshold_seconds=0, cycle_cooldown_seconds=0)
    result = runtime.run_cycle_now()
    assert result["status"] == "learned"
    snap = runtime.snapshot()
    assert snap["total_cycles"] == 1
    assert snap["learned_cycles"] == 1
    assert snap["failed_cycles"] == 0
    assert engine.fabric.stats()["records"] == 1


def test_activity_resets_idle_window_budget(tmp_path):
    engine = CuriosityEngine(tmp_path / "engine")
    engine.observe_prompt("operating system scheduler fairness")
    runtime = IdleCuriosityRuntime(engine, _researcher, idle_threshold_seconds=0, cycle_cooldown_seconds=0, max_cycles_per_idle_window=1)
    runtime.run_cycle_now()
    assert runtime.snapshot()["cycles_this_window"] == 1
    assert runtime.eligible() is False
    runtime.mark_activity("operating system scheduler starvation")
    assert runtime.snapshot()["cycles_this_window"] == 0


def test_failed_research_is_counted_without_killing_runtime(tmp_path):
    engine = CuriosityEngine(tmp_path / "engine")
    engine.observe_prompt("fault injection distributed systems")
    def explode(inquiry, context):
        raise RuntimeError("research provider unavailable")
    runtime = IdleCuriosityRuntime(engine, explode, idle_threshold_seconds=0, cycle_cooldown_seconds=0)
    result = runtime.run_cycle_now()
    assert result["status"] == "error"
    snap = runtime.snapshot()
    assert snap["failed_cycles"] == 1
    assert snap["total_cycles"] == 1
    assert "RuntimeError" in snap["last_error"]


def test_background_thread_stops_cleanly(tmp_path):
    engine = CuriosityEngine(tmp_path / "engine")
    runtime = IdleCuriosityRuntime(engine, _researcher, idle_threshold_seconds=999, poll_seconds=0.01)
    assert runtime.start() is True
    assert runtime.start() is False
    time.sleep(0.02)
    assert runtime.running is True
    assert runtime.stop(join_timeout=1) is True
    assert runtime.running is False
