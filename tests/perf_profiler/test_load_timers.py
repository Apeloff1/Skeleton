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
