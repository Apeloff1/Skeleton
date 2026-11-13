import pytest

from skeleton.qualification.gates import evaluate
from skeleton.qualification.gates._stats import linear_slope, percentile


def test_percentile_nearest_rank():
    v = list(range(1, 101))
    assert percentile(v, 50) == 50 and percentile(v, 95) == 95 and percentile(v, 100) == 100
    assert percentile([7], 99) == 7
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1], 101)


def test_linear_slope():
    assert linear_slope([1, 3, 5]) == pytest.approx(2)
    assert linear_slope([5]) == 0
    assert linear_slope([1, 1], [2, 2]) == 0
    with pytest.raises(ValueError):
        linear_slope([1, 2], [1])


FPS = {"profiles": [30, 60], "sim_hz": 60, "min_ratio": 0.95}


def run(ms, sim=60, h="s1"):
    return {"frame_ms": ms, "sim_hz": sim, "sim_state_hash": h}


def test_fps_pass_and_fail():
    ok = {"runs": {"30": run([33.0] * 20), "60": run([16.0] * 20)}}
    assert evaluate("fps", FPS, ok)[0] == []
    slow = {"runs": {"30": run([33.0] * 20), "60": run([16.0] * 18 + [25.0, 25.0])}}
    reasons, m = evaluate("fps", FPS, slow)
    assert any("60 fps: p95" in r for r in reasons) and m["60.p95_fps"] == 40.0


def test_fps_sim_rate_and_divergence():
    data = {"runs": {"30": run([30.0], sim=30), "60": run([16.0], h="s2")}}
    reasons, _ = evaluate("fps", FPS, data)
    assert any("sim rate 30" in r for r in reasons)
    assert any("diverged" in r for r in reasons)


def test_fps_missing_runs():
    assert "runs" in evaluate("fps", FPS, {})[0][0]
    reasons, _ = evaluate("fps", FPS, {"runs": {"30": run([])}})
    assert any("empty" in r for r in reasons) and any("no run recorded for 60" in r for r in reasons)


PERF = {"metric": "load", "budgets_ms": {"p50": 10, "p99": 20}, "min_samples": 10}


def test_perf():
    assert evaluate("perf", PERF, {"samples_ms": [5] * 100})[0] == []
    reasons, m = evaluate("perf", PERF, {"samples_ms": [5] * 98 + [50, 50]})
    assert reasons == ["load p99 50 ms over budget 20 ms"] and m["p50"] == 5
    assert "only 3" in evaluate("perf", PERF, {"samples_ms": [1, 2, 3]})[0][0]
    assert evaluate("perf", PERF, {})[0] == ["evidence missing 'samples_ms'"]


SOAK = {"min_hours": 24.0, "max_rss_mb_per_hour": 1.0, "max_error_rate": 0.01, "max_restarts": 0}


def soak(**o):
    d = {"hours": 24, "rss_mb": [100, 101, 100, 101], "requests": 1000, "errors": 1, "restarts": 0}
    d.update(o)
    return d


def test_soak_pass():
    assert evaluate("soak", SOAK, soak())[0] == []


@pytest.mark.parametrize("over,needle", [
    ({"hours": 2}, "need 24"),
    ({"rss_mb": [100, 200, 300]}, "memory grows"),
    ({"rss_mb": [1, 2]}, "at least 3"),
    ({"errors": 50}, "error rate"),
    ({"requests": 0}, "error rate"),
    ({"restarts": 2}, "restarts"),
])
def test_soak_failures(over, needle):
    assert any(needle in r for r in evaluate("soak", SOAK, soak(**over))[0])


RET = {"min_days": {"traces": 14, "audit": 365}, "pii_max_days": 30}


def test_retention():
    ok = {"signals": {"traces": {"days": 14}, "audit": {"days": 400}, "logs": {"days": 30, "pii": True}}}
    assert evaluate("retention", RET, ok)[0] == []
    bad = {"signals": {"traces": {"days": 7}, "logs": {"days": 90, "pii": True}}}
    reasons, _ = evaluate("retention", RET, bad)
    assert "signal 'audit' has no retention policy" in reasons
    assert any("traces' kept 7" in r for r in reasons)
    assert any("PII for 90" in r for r in reasons)


def test_replay():
    orig = [f"h{i}" for i in range(20)]
    assert evaluate("replay", {"min_ticks": 10}, {"snapshot_tick": 5, "original": orig, "restored": orig[5:]})[0] == []
    rest = orig[5:]; rest[3] = "zz"
    reasons, m = evaluate("replay", {"min_ticks": 10}, {"snapshot_tick": 5, "original": orig, "restored": rest})
    assert reasons == ["divergence at tick 8"] and m["first_divergence"] == 8
    short = evaluate("replay", {"min_ticks": 100}, {"snapshot_tick": 5, "original": orig, "restored": orig[5:]})[0]
    assert "need 100" in short[0]


PROM = {"max_canary_regression": 0.02}


def stages(*names, receipt=True, reg=0.0):
    return [{"stage": n, "receipt": "r" if receipt else "", "regression": reg} for n in names]


def test_promotion():
    full = {"stages": stages("shadow", "canary", "production"), "rollback_tested": True}
    assert evaluate("promotion", PROM, full)[0] == []
    assert evaluate("promotion", PROM, {"stages": stages("shadow")})[0] == []
    r = evaluate("promotion", PROM, {"stages": stages("canary", "shadow")})[0]
    assert any("out of order" in x for x in r)
    r = evaluate("promotion", PROM, {"stages": stages("shadow", "canary", "production", reg=0.1)})[0]
    assert any("canary regression" in x for x in r) and any("rollback" in x for x in r)
    r = evaluate("promotion", PROM, {"stages": stages("shadow", receipt=False)})[0]
    assert r == ["stage 'shadow' has no release receipt"]
