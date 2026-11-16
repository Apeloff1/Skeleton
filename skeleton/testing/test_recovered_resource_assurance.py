"""Resource admission and source-only model custody integration regression source."""
from hashlib import sha256
import json
import os
import struct

import pytest

from skeleton.app.offline_cpu_budget import CpuTopology, MemoryTopology
from skeleton.app.offline_energy_budget import PowerObservation
from skeleton.app.resource_assurance import AdmissionGate, AdmissionPolicy, ResourceSample
from skeleton.app import resource_assurance_runner as runner
from skeleton.app.recovered_evidence import EvidenceError


def sample(n, *, temp=45, memory=4*1024**3, battery=100, ac=True):
    return ResourceSample(n-1,n,CpuTopology(8,4,8,1024**2,"test","test","test","test"),
                          MemoryTopology(8*1024**3,memory,"test"),
                          PowerObservation(battery,ac,temp,"test","test","test"))


def test_hysteresis_admits_then_immediately_sheds():
    gate=AdmissionGate(AdmissionPolicy())
    for n in (10,20):
        assert gate.step(sample(n),now_ns=n)["workers"]==0
    assert gate.step(sample(30),now_ns=30)["workers"]==1
    assert gate.step(sample(40,temp=100),now_ns=40)["workers"]==0


def test_unknown_memory_and_stale_observations_hold():
    gate=AdmissionGate(AdmissionPolicy())
    for n in (10,20,30):
        assert gate.step(sample(n,memory=None),now_ns=n)["workers"]==0
    assert gate.step(sample(31),now_ns=10**10)["workers"]==0


def test_repeated_sample_does_not_grant():
    gate=AdmissionGate(AdmissionPolicy())
    gate.step(sample(10),now_ns=10)
    assert gate.step(sample(10),now_ns=11)["workers"]==0


def test_pressure_holds_actual_owner_invocation(monkeypatch):
    now=iter(range(10,1000,10))
    monkeypatch.setattr(runner.time,"monotonic_ns",lambda:next(now))
    monkeypatch.setattr(runner,"observe",lambda:sample(1,temp=100))
    monkeypatch.setattr(runner,"qualify",lambda *a,**k:pytest.fail("held owner executed"))
    result=runner.run_campaign(["trust-gates"],authorized=True,
                               policy=AdmissionPolicy(interval_ms=0))
    assert result["held_suites"]==1
    assert result["accounted_cases"]==0
    assert not result["native_model_tested"]


def test_real_owner_runs_after_healthy_gate(monkeypatch):
    step=iter(range(10,1000,10))
    monkeypatch.setattr(runner.time,"monotonic_ns",lambda:next(step))
    monkeypatch.setattr(runner,"observe",lambda:sample(next(step)))
    result=runner.run_campaign(["trust-gates"],authorized=True,
                               policy=AdmissionPolicy(interval_ms=0))
    assert result["completed_selection"]
    assert result["accounted_cases"]==240
    assert result["sequential_execution"]
    assert not result["physical_resource_reservation"]


def test_previous_report_is_not_execution_credit(monkeypatch):
    monkeypatch.setattr(runner,"observe",lambda:pytest.fail("unverified history accepted"))
    with pytest.raises(EvidenceError):
        runner.run_campaign(["trust-gates"],authorized=True,previous={},previous_digest="a"*64)


def test_explicit_authorization_precedes_probe(monkeypatch):
    monkeypatch.setattr(runner,"observe",lambda:pytest.fail("unauthorized probe"))
    with pytest.raises(PermissionError):
        runner.run_campaign(["trust-gates"],authorized=False)


def test_gguf_source_route_denies_before_inspection(monkeypatch):
    from skeleton.app import gguf_source_preflight_cli as cli
    monkeypatch.setattr(cli,"inspect_gguf",lambda *a,**k:pytest.fail("unauthorized source read"))
    with pytest.raises(PermissionError):
        cli.qualify_source("no-file",expected_sha256="a"*64,max_bytes=24,authorized=False)


def test_gguf_route_propagates_canonical_observation(monkeypatch):
    from skeleton.app import gguf_source_preflight_cli as cli
    from skeleton.native.gguf_preflight import GGUFHeader
    monkeypatch.setattr(cli,"inspect_gguf",lambda *a,**k:GGUFHeader(3,1,0,24,"a"*64))
    report=cli.qualify_source("model",expected_sha256="a"*64,max_bytes=24,authorized=True)
    assert report["header"]["sha256"]=="a"*64
    assert not report["full_tensor_validation"]
    assert not report["native_model_loaded"]


@pytest.mark.parametrize("route",["offline-cpu-budget","offline-energy-budget",
                                  "resource-assurance","gguf-source-preflight"])
def test_installed_help(route,capsys):
    from skeleton.__main__ import main
    with pytest.raises(SystemExit) as e:
        main([route,"--help"])
    assert e.value.code==0
    assert "usage:" in capsys.readouterr().out.lower()
