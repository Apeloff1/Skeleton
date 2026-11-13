"""Adversarial quarantine performance-gate acceptance."""
from __future__ import annotations
import json
from unittest.mock import patch
import pytest
from skeleton.perfgate import Baseline, SoakConfig, compare, load_baseline, load_budgets, summarize
from skeleton.perfgate.cli import main
from skeleton.perfgate.soak import SoakResult


@pytest.mark.parametrize("value",[float("nan"),float("inf"),True,-1.0])
def test_invalid_latency_never_certifies(value):
    with pytest.raises(ValueError):
        summarize([value])


def test_empty_measurements_block_without_budgets(capsys):
    with patch("skeleton.perfgate.cli.run_soak",return_value=SoakResult("noop")):
        assert main(["--workload","noop","--iterations","1","--json"])==1
    doc=json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert doc["ok"] is False and doc["release_certified"] is False


def test_missing_budgeted_or_baseline_workload_blocks():
    bs=load_budgets({"version":1,"workloads":{"required":{"p95_ms":5}}})
    assert bs.check({"other":summarize([1])})
    base=Baseline.from_summaries({"required":summarize([1])})
    assert not compare(base,{"other":summarize([1])}).ok


def test_baseline_nonfinite_duplicate_or_unknown_fields_block(tmp_path):
    p=tmp_path/"base.json"
    for body in ('{"version":1,"workloads":{},"workloads":{}}',
                 '{"version":1,"workloads":{"a":{"p50_ms":NaN}}}',
                 '{"version":1,"workloads":{},"unexpected":true}'):
        p.write_text(body)
        with pytest.raises(ValueError):
            load_baseline(p)


def test_invalid_configuration_nonfinite():
    for v in (float("nan"),float("inf"),True,-1):
        with pytest.raises(ValueError):
            load_budgets({"version":1,"workloads":{"a":{"p95_ms":v}}})
        with pytest.raises(ValueError):
            compare(Baseline(),{},tolerance=v)
    for kw in ({"duration_s":float("nan")},{"iterations":100001},
               {"warmup":10001},{"iterations":True}):
        with pytest.raises(ValueError):
            SoakConfig(**kw)


def test_warmup_failures_cannot_be_reported_successful(capsys):
    from skeleton.perfgate.soak import run_soak
    calls={"n":0}
    def flaky():
        calls["n"]+=1
        if calls["n"]==1:raise RuntimeError("do-not-log-private-message")
    outcome=run_soak("broken",flaky,SoakConfig(iterations=1,warmup=1))
    assert outcome.warmup_errors==1


def test_empty_or_all_error_budgeted_measurement_is_not_a_pass():
    from skeleton.perfgate.budget import MissingBudgetedWorkload
    budgets=load_budgets({"version":1,"workloads":{"required":{"p95_ms":500}}})
    for stats in (summarize([]),summarize([],errors=3),summarize([0.0])):
        failures=budgets.check({"required":stats})
        assert len(failures)==1 and isinstance(failures[0],MissingBudgetedWorkload)


def test_baseline_cannot_be_published_without_positive_measured_sample():
    for sample in (summarize([]),summarize([],errors=3),summarize([0.0])):
        with pytest.raises(ValueError,match="measured"):
            Baseline.from_summaries({"unmeasured":sample})
    baseline=Baseline.from_summaries({"required":summarize([1.0])})
    for sample in (summarize([]),summarize([],errors=2),summarize([0.0])):
        report=compare(baseline,{"required":sample})
        assert not report.ok and report.missing == ["required"]


def test_invalid_summary_and_zero_initial_drift_fail_closed():
    from skeleton.perfgate.stats import Summary
    for name,value in (("mean_ms",float("nan")),
                       ("p95_ms",float("inf")),
                       ("error_rate",1.1),
                       ("drift_ratio",float("nan"))):
        values={"count":1,"errors":0,"mean_ms":1.0,"p50_ms":1.0,
                "p95_ms":1.0,"p99_ms":1.0,"max_ms":1.0,
                "error_rate":0.0,"drift_ratio":1.0}
        values[name]=value
        with pytest.raises(ValueError):
            Summary(**values)
    with pytest.raises(ValueError,match="drift"):
        summarize([0.0,0.0,10.0])


def test_zero_duration_clock_does_not_create_positive_soak_evidence():
    from skeleton.perfgate.soak import run_soak
    outcome=run_soak("unmeasured",lambda:None,SoakConfig(iterations=3,warmup=0),
                     clock=lambda:1.0)
    assert outcome.aborted is True
    assert outcome.samples_ms==[]
    assert outcome.errors==["InvalidClock"]
