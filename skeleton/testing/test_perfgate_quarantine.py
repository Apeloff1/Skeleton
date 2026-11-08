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
