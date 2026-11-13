import copy
import json

import pytest

from skeleton.perf_profiler.clock import DeterministicClock
from skeleton.perf_profiler.load_timers import LoadTimer, verify_report


def _timer(script, **kw):
    return LoadTimer(label="level-1", clock=DeterministicClock(script=script), **kw)


def test_nested_phases_produce_tree_self_time_and_flat_paths():
    # reads: level.start, tex.start(+5), tex.end(+20), audio.start(+0), audio.end(+10), level.end(+5)
    timer = _timer([5, 20, 0, 10, 5])
    with timer.phase("level"):
        with timer.phase("textures"):
            pass
        with timer.phase("audio"):
            pass
    payload = timer.report().payload
    assert payload["total_ms"] == 40.0
    flat = {p["name"]: p for p in payload["phases"]}
    assert flat["level"]["duration_ms"] == 40.0
    assert flat["level"]["self_ms"] == 10.0
    assert flat["level/textures"]["duration_ms"] == 20.0
    assert flat["level/audio"]["duration_ms"] == 10.0
    assert payload["ok"] is True


def test_report_is_deterministic_and_verifiable():
    def run():
        t = _timer([3, 4])
        with t.phase("a"):
            with t.phase("b"):
                pass
        return t.report()

    r1, r2 = run(), run()
    assert r1.digest == r2.digest
    assert verify_report(json.loads(r1.to_json()))


def test_tampered_report_fails_verification():
    t = _timer([7])
    with t.phase("a"):
        pass
    data = t.report().to_dict()
    bad = copy.deepcopy(data)
    bad["payload"]["total_ms"] = 1.0
    assert not verify_report(bad)
    bad = copy.deepcopy(data)
    bad["payload"]["schema"] = "other"
    bad["sha256"] = data["sha256"]
    assert not verify_report(bad)
    assert not verify_report({"payload": data["payload"]})
    assert not verify_report({"payload": "x", "sha256": "y"})


def test_budget_exceeded_marks_not_ok():
    t = _timer([30], budget_ms=25)
    with t.phase("boot"):
        pass
    assert t.report().payload["ok"] is False


def test_exception_is_recorded_and_reraised():
    t = _timer([2, 2])
    with pytest.raises(KeyError):
        with t.phase("level"):
            with t.phase("shaders"):
                raise KeyError("missing")
    payload = t.report().payload
    assert payload["ok"] is False
    assert {"phase": "level/shaders", "error": "KeyError"} in payload["errors"]


def test_open_phase_refuses_report():
    t = _timer([])
    cm = t.phase("open")
    cm.__enter__()
    with pytest.raises(RuntimeError):
        t.report()
    cm.__exit__(None, None, None)
    t.report()


def test_phase_name_validation():
    t = _timer([1, 1])
    with pytest.raises(ValueError):
        with t.phase("a/b"):
            pass
    with t.phase("a"):
        pass
    with pytest.raises(ValueError):
        with t.phase("a"):
            pass
    with pytest.raises(ValueError):
        LoadTimer(budget_ms=0)


def test_load_timer_rejects_nonfinite_budgets_and_unbounded_labels():
    import pytest
    for value in (float("nan"), float("inf"), float("-inf"), 0, -1, True):
        with pytest.raises(ValueError, match="budget_ms"):
            LoadTimer(budget_ms=value)
    with pytest.raises(ValueError, match="label"):
        LoadTimer(label="x" * 129)
    timer = LoadTimer()
    for name in ("", "x" * 129, 1, "a/b"):
        with pytest.raises(ValueError, match="phase name"):
            with timer.phase(name):
                pass


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 10**1000, "10", True])
def test_bad_exit_clock_fails_closed_and_does_not_strand_open_phase(bad):
    class Clock:
        reads = 0

        def now_ms(self):
            self.reads += 1
            return (0.0, bad, 10.0, 12.0)[self.reads - 1]

    timer = LoadTimer(clock=Clock())
    with pytest.raises(ValueError, match="timestamp must be finite"):
        with timer.phase("bad"):
            pass
    assert timer.report().payload["ok"] is False
    with timer.phase("recovered"):
        pass
    payload = timer.report().payload
    assert payload["ok"] is False
    assert payload["phases"][-1]["duration_ms"] == 2.0
    assert {"phase": "bad", "error": "ValueError"} in payload["errors"]


def test_bad_start_clock_does_not_publish_partial_node():
    class Clock:
        reads = 0

        def now_ms(self):
            self.reads += 1
            return (float("nan"), 1.0, 2.0)[self.reads - 1]

    timer = LoadTimer(clock=Clock())
    with pytest.raises(ValueError, match="timestamp must be finite"):
        with timer.phase("rejected"):
            pass
    with timer.phase("accepted"):
        pass
    assert [node["name"] for node in timer.report().payload["tree"]] == ["accepted"]


def test_clock_failure_does_not_mask_original_body_exception():
    class Clock:
        reads = 0

        def now_ms(self):
            self.reads += 1
            return 0.0 if self.reads == 1 else float("nan")

    timer = LoadTimer(clock=Clock())
    with pytest.raises(KeyError, match="original"):
        with timer.phase("broken"):
            raise KeyError("original")
    errors = timer.report().payload["errors"]
    assert {"phase": "broken", "error": "KeyError"} in errors
    assert {"phase": "broken", "error": "ValueError"} in errors


def test_clock_overflow_delta_unwinds_and_marks_report_invalid():
    class Clock:
        reads = 0

        def now_ms(self):
            self.reads += 1
            return -1e308 if self.reads == 1 else 1e308

    timer = LoadTimer(clock=Clock())
    with pytest.raises(ValueError, match="finite non-negative duration"):
        with timer.phase("overflow"):
            pass
    assert timer.report().payload["ok"] is False


def test_load_timer_bounds_node_count_and_depth(monkeypatch):
    from contextlib import ExitStack
    from skeleton.perf_profiler import load_timers

    monkeypatch.setattr(load_timers, "MAX_PHASE_DEPTH", 2)
    timer = LoadTimer(clock=DeterministicClock())
    with ExitStack() as stack:
        stack.enter_context(timer.phase("outer"))
        stack.enter_context(timer.phase("inner"))
        with pytest.raises(ValueError, match="bounded depth"):
            stack.enter_context(timer.phase("excess"))
    assert len(timer.report().payload["phases"]) == 2

    monkeypatch.setattr(load_timers, "MAX_PHASE_NODES", 2)
    timer = LoadTimer(clock=DeterministicClock())
    with timer.phase("first"):
        pass
    with timer.phase("second"):
        pass
    with pytest.raises(ValueError, match="bounded node limit"):
        with timer.phase("third"):
            pass
    assert len(timer.report().payload["tree"]) == 2


def test_budget_overflow_rejected_as_usage_value_error():
    with pytest.raises(ValueError, match="budget_ms"):
        LoadTimer(budget_ms=10**1000)


def test_overflowed_total_cannot_be_sealed_as_nonfinite_json():
    class Clock:
        reads = 0

        def now_ms(self):
            self.reads += 1
            return 0.0 if self.reads % 2 else 1e308

    timer = LoadTimer(clock=Clock())
    with timer.phase("first"):
        pass
    with timer.phase("second"):
        pass
    with pytest.raises(ValueError, match="total exceeds finite bound"):
        timer.report()
