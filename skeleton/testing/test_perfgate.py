"""GF-M: soak harness, perf budgets, baseline regression gate."""
from __future__ import annotations

import json

import pytest

from skeleton.perfgate import (Baseline, SoakConfig, compare, load_baseline, load_budgets,
                               percentile, run_soak, save_baseline, summarize)
from skeleton.perfgate.cli import main
from skeleton.perfgate.workloads import resolve


class FakeClock:
    def __init__(self, steps):
        self.t = 0.0
        self.steps = iter(steps)

    def __call__(self):
        return self.t

    def advance(self):
        self.t += next(self.steps)


def test_percentile_interpolates():
    assert percentile([1, 2, 3, 4], 50) == 2.5
    assert percentile([5], 99) == 5
    assert percentile([1, 2, 3, 4, 5], 100) == 5
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1], 101)


def test_summarize_drift_and_errors():
    s = summarize([10, 10, 10, 20, 20, 20], errors=2)
    assert s.count == 8 and s.errors == 2
    assert s.error_rate == pytest.approx(0.25)
    assert s.drift_ratio == pytest.approx(2.0)
    assert summarize([], errors=0).error_rate == 0.0
    assert summarize([], errors=3).error_rate == 1.0


def test_soak_uses_clock_and_counts_iterations():
    clock = FakeClock([0.005] * 100)
    res = run_soak("w", clock.advance, SoakConfig(iterations=5, warmup=2), clock=clock)
    assert len(res.samples_ms) == 5
    assert all(ms == pytest.approx(5.0) for ms in res.samples_ms)


def test_soak_aborts_on_consecutive_errors():
    def boom():
        raise RuntimeError("x")
    res = run_soak("w", boom, SoakConfig(iterations=10, warmup=0, max_consecutive_errors=3))
    assert res.aborted and len(res.errors) == 3 and res.summary.error_rate == 1.0


def test_soak_error_streak_resets():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] % 2:
            raise ValueError("odd")
    res = run_soak("w", flaky, SoakConfig(iterations=10, warmup=0, max_consecutive_errors=2))
    assert not res.aborted and len(res.errors) == 5 and len(res.samples_ms) == 5


def test_soak_stops_on_duration():
    clock = FakeClock([1.0] * 100)
    res = run_soak("w", clock.advance, SoakConfig(iterations=50, warmup=0, duration_s=3),
                   clock=clock)
    assert res.stopped_by_duration and len(res.samples_ms) == 3


@pytest.mark.parametrize("kw", [{"iterations": 0}, {"warmup": -1}, {"duration_s": 0},
                                {"max_consecutive_errors": 0}])
def test_soak_config_validation(kw):
    with pytest.raises(ValueError):
        SoakConfig(**kw)


def test_budget_violations():
    bs = load_budgets({"version": 1, "workloads": {"a": {"p95_ms": 10, "error_rate": 0}}})
    v = bs.check({"a": summarize([5, 50], errors=1)})
    assert {x.metric for x in v} == {"p95_ms", "error_rate"}
    assert bs.check({"a": summarize([1, 2])}) == []
    assert any("not measured" in str(v) for v in bs.check({"other": summarize([999])}))


@pytest.mark.parametrize("bad", [{"version": 2, "workloads": {}}, {"version": 1},
                                 {"version": 1, "workloads": {"a": {"bogus": 1}}},
                                 {"version": 1, "workloads": {"a": {"p95_ms": -1}}}])
def test_budget_rejects_bad_config(bad):
    with pytest.raises(ValueError):
        load_budgets(bad)


def test_default_budget_file_loads():
    from pathlib import Path
    import skeleton.perfgate as pg
    bs = load_budgets(Path(pg.__file__).with_name("budgets.default.json"))
    assert "forge_walk:soulslike" in bs.budgets


def test_baseline_roundtrip_and_compare(tmp_path):
    base = Baseline.from_summaries({"a": summarize([100] * 10), "gone": summarize([1])})
    path = tmp_path / "b" / "base.json"
    save_baseline(base, path)
    loaded = load_baseline(path)
    assert loaded.workloads == base.workloads
    rep = compare(loaded, {"a": summarize([150] * 10), "fresh": summarize([1])})
    assert not rep.ok
    assert {d.metric for d in rep.regressions} == {"p50_ms", "p95_ms", "p99_ms", "mean_ms"}
    assert rep.missing == ["gone"] and rep.new == ["fresh"]
    assert compare(loaded, {"a": summarize([110] * 10)}).ok
    assert compare(loaded, {"a": summarize([50] * 10)}).improvements


def test_compare_noise_floor_ignores_tiny_deltas():
    base = Baseline.from_summaries({"a": summarize([1.0] * 5)})
    assert compare(base, {"a": summarize([2.5] * 5)}).ok  # +1.5ms < 2ms floor
    assert not compare(base, {"a": summarize([2.5] * 5)}, noise_floor_ms=0).ok


def test_resolve_workloads():
    assert resolve("noop")() is None
    assert callable(resolve("forge_walk:soulslike"))
    with pytest.raises(KeyError):
        resolve("nope")


def test_cli_pass_writes_baseline_then_gates(tmp_path, capsys):
    base = tmp_path / "base.json"
    assert main(["--workload", "noop", "--iterations", "5", "--write-baseline", str(base),
                 "--json"]) == 0
    line = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(line)["ok"] is True
    assert main(["--workload", "noop", "--iterations", "5", "--baseline", str(base)]) == 0


def test_cli_budget_failure(tmp_path):
    b = tmp_path / "b.json"
    b.write_text(json.dumps({"version": 1, "workloads": {"noop": {"p95_ms": 0, "max_ms": 0}}}))
    # noop takes > 0 ms of wall time, so a zero budget must fail
    assert main(["--workload", "noop", "--iterations", "3", "--budgets", str(b)]) == 1


def test_cli_usage_errors(tmp_path):
    assert main([]) == 2
    assert main(["--workload", "nope"]) == 2
    assert main(["--workload", "noop", "--iterations", "0"]) == 2
    assert main(["--workload", "noop", "--budgets", str(tmp_path / "missing.json")]) == 2


def test_ai_mirror_matches():
    from pathlib import Path
    import skeleton.perfgate as a
    import skeleton.ai.perfgate as b
    da, db = Path(a.__file__).parent, Path(b.__file__).parent
    names = sorted(p.name for p in da.iterdir() if p.is_file())
    assert names == sorted(p.name for p in db.iterdir() if p.is_file())
    for n in names:
        assert (da / n).read_bytes() == (db / n).read_bytes(), n


def test_forge_walk_soak_smoke():
    res = run_soak("forge_walk:soulslike", resolve("forge_walk:soulslike"),
                   SoakConfig(iterations=2, warmup=0))
    assert not res.errors, res.errors
