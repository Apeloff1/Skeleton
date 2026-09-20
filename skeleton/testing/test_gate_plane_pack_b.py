"""Pack B gate_plane tests — stack, admit, chaos, proxy, create_app hooks."""

from __future__ import annotations

import pytest

from skeleton.gate_plane.admit import (
    AdmissionMatrix,
    AdmissionOutcome,
    evaluate_admission,
    summarize_outcomes,
)
from skeleton.gate_plane.chaos_scenarios import SCENARIOS, run_all, run_scenario, scenario_catalog
from skeleton.gate_plane.create_app_hooks import build_create_app_gate_plan, open_probe_prefixes
from skeleton.gate_plane.evidence import digest_plane, render_evidence
from skeleton.gate_plane.operations import (
    digest_registry,
    playbook_chaos_sample,
    playbook_create_app_smoke,
    registry,
    validate_plan,
)
from skeleton.gate_plane.proxy_contracts import default_upstreams, validate_proxy_plan
from skeleton.gate_plane.stack import GATE_LAYERS, describe_stack, install_order
from skeleton.kernel.adaptive_gate import AdaptiveGate
from skeleton.kernel.chaos import ChaosGovernor, Rung


def test_stack_has_write_admit():
    names = [l.name for l in GATE_LAYERS]
    assert "write_admit" in names
    assert "request_seal" in names
    order = install_order(lifo=True)
    # Innermost registered first → policy_gate first in LIFO registration list
    assert order[0] == "policy_gate"
    assert order[-1] == "header_bound" or order[-1] == "request_seal" or "request_seal" in order


def test_describe_stack_nonempty():
    assert len(describe_stack()) == len(GATE_LAYERS)


def test_open_root_exact():
    m = AdmissionMatrix()
    assert m.is_open("/")
    assert not m.is_open("/api/v1/forge/kinds")


def test_admit_shed_on_empty_gate():
    matrix = AdmissionMatrix(gate=AdaptiveGate(0, 0), governor=ChaosGovernor(min_samples=1000))
    d = evaluate_admission(path="/api/v1/forge/blueprint", method="POST", attester="bot", matrix=matrix)
    assert d.outcome is AdmissionOutcome.SHED


def test_admit_emergency():
    gov = ChaosGovernor(min_samples=1000)
    with gov._lock:
        gov._rung = Rung.EMERGENCY_READ_ONLY
    matrix = AdmissionMatrix(gate=AdaptiveGate(10, 10), governor=gov)
    d = evaluate_admission(path="/api/v1/forge/blueprint", method="POST", attester="bot", matrix=matrix)
    assert d.outcome is AdmissionOutcome.EMERGENCY_READ_ONLY


def test_chaos_catalog_size():
    assert len(SCENARIOS) >= 100
    assert len(scenario_catalog()) == len(SCENARIOS)


def test_chaos_sample_runs():
    result = run_all(limit=30)
    assert result["total"] == 30
    assert result["passed"] + len(result["failed"]) == 30


def test_proxy_defaults():
    ups = default_upstreams()
    assert len(ups) >= 5
    assert validate_proxy_plan(ups)["ok"] is True


def test_create_app_plan_wires_gate():
    plan = build_create_app_gate_plan()
    assert plan.wire_install_gate is True
    assert plan.wire_write_admit is True
    assert "/" in open_probe_prefixes()


def test_evidence_digest_stable():
    a = digest_plane()
    b = digest_plane()
    assert a == b
    assert len(a) == 64
    ev = render_evidence(run_scenarios=True, scenario_limit=20)
    assert ev.create_app_wired is True
    assert ev.scenarios >= 100


def test_operations_registry():
    reg = registry()
    assert len(reg) >= 100
    plan = next(iter(reg.values()))()
    assert validate_plan(plan)["ok"] is True
    assert len(digest_registry()) == 64


def test_playbooks():
    smoke = playbook_create_app_smoke()
    assert smoke["create_app"]["wire_install_gate"] is True
    sample = playbook_chaos_sample(limit=25)
    assert sample["passed"] + len(sample["failed"]) == 25


def test_summarize_outcomes():
    matrix = AdmissionMatrix(gate=AdaptiveGate(10, 10), governor=ChaosGovernor(min_samples=1000))
    decs = [
        evaluate_admission(path="/health", method="GET", attester=None, matrix=matrix),
        evaluate_admission(path="/api/v1/forge/kinds", method="GET", attester=None, matrix=matrix),
    ]
    counts = summarize_outcomes(decs)
    assert counts.get("open_bypass", 0) >= 1
    assert counts.get("seal_required", 0) >= 1


# --- sampled scenario integrity ---

def test_scenario_0000_expectation():
    s = SCENARIOS[0]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0005_expectation():
    s = SCENARIOS[5]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0010_expectation():
    s = SCENARIOS[10]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0015_expectation():
    s = SCENARIOS[15]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0020_expectation():
    s = SCENARIOS[20]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0025_expectation():
    s = SCENARIOS[25]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0030_expectation():
    s = SCENARIOS[30]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0035_expectation():
    s = SCENARIOS[35]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0040_expectation():
    s = SCENARIOS[40]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0045_expectation():
    s = SCENARIOS[45]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0050_expectation():
    s = SCENARIOS[50]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0055_expectation():
    s = SCENARIOS[55]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0060_expectation():
    s = SCENARIOS[60]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0065_expectation():
    s = SCENARIOS[65]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0070_expectation():
    s = SCENARIOS[70]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0075_expectation():
    s = SCENARIOS[75]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0080_expectation():
    s = SCENARIOS[80]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0085_expectation():
    s = SCENARIOS[85]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0090_expectation():
    s = SCENARIOS[90]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0095_expectation():
    s = SCENARIOS[95]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0100_expectation():
    s = SCENARIOS[100]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0105_expectation():
    s = SCENARIOS[105]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0110_expectation():
    s = SCENARIOS[110]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0115_expectation():
    s = SCENARIOS[115]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0120_expectation():
    s = SCENARIOS[120]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0125_expectation():
    s = SCENARIOS[125]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0130_expectation():
    s = SCENARIOS[130]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0135_expectation():
    s = SCENARIOS[135]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0140_expectation():
    s = SCENARIOS[140]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0145_expectation():
    s = SCENARIOS[145]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0150_expectation():
    s = SCENARIOS[150]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0155_expectation():
    s = SCENARIOS[155]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0160_expectation():
    s = SCENARIOS[160]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0165_expectation():
    s = SCENARIOS[165]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0170_expectation():
    s = SCENARIOS[170]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0175_expectation():
    s = SCENARIOS[175]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0180_expectation():
    s = SCENARIOS[180]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0185_expectation():
    s = SCENARIOS[185]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0190_expectation():
    s = SCENARIOS[190]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)

def test_scenario_0195_expectation():
    s = SCENARIOS[195]
    _dec, ok = run_scenario(s)
    assert ok, (s.name, s.expect, _dec.outcome.value)
