from __future__ import annotations
import importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"machine"/"essentials_1000.json"
SCHED=ROOT/"machine"/"project_self_improvement_idle_scheduler.json"
CLOSURE=ROOT/"machine"/"essentials_1000_closure_protocol.json"
LEDGER=ROOT/"machine"/"essentials_1000_gap_ledger.json"
PRIORITY=ROOT/"machine"/"essentials_1000_priority_policy.json"
FRONTIER=ROOT/"machine"/"essentials_1000_execution_frontier.json"
MODULE=ROOT/"scripts"/"check_essentials_1000.py"

def _m():
    spec=importlib.util.spec_from_file_location("check_essentials_1000",MODULE)
    assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def _d(): return json.loads(DATA.read_text(encoding="utf-8"))
def _s(): return json.loads(SCHED.read_text(encoding="utf-8"))
def _c(): return json.loads(CLOSURE.read_text(encoding="utf-8"))
def _l(): return json.loads(LEDGER.read_text(encoding="utf-8"))
def _p(): return json.loads(PRIORITY.read_text(encoding="utf-8"))
def _f(): return json.loads(FRONTIER.read_text(encoding="utf-8"))

def test_contract_is_valid(): assert _m().validate(_d(),_s(),_c(),_l(),_p(),_f())==[]
def test_exact_1000_and_100_strata():
    d=_d()
    assert [x["id"] for x in d["levels"]]==[f"ESS1000-{i:04d}" for i in range(1,1001)]
    assert len(d["strata"])==100 and len(d["construction_waves"])==100
def test_every_essential_is_non_compensable_and_paired():
    for i,l in enumerate(_d()["levels"],1):
        assert l["mandatory_for_complete_platform"] is True
        assert l["compensable_by_advanced_feature"] is False
        assert l["documentation_alone_sufficient"] is False
        assert l["paired_psi_layer"]==f"PSI1000-{i:04d}"
def test_starts_unsigned():
    d=_d()
    assert d["completion"]["signed_complete"]==0
    assert d["completion"]["essentials_1000_qualified"] is False
    assert d["completion"]["implementation_claim"] is False
    assert all(not x["complete"] for x in d["levels"])
def test_scheduler_prioritizes_unresolved_essentials():
    s=_s()
    assert s["authority"]["essentials"]=="machine/essentials_1000.json"
    p=s["essential_priority"]
    assert p["enabled"] is True
    assert p["mapping"]=="ESS1000-nnnn -> PSI1000-nnnn"
    assert p["unresolved_essential_priority"]=="above_optional_same_domain"
def test_disabled_capability_cannot_escape_baseline():
    laws="\n".join(_d()["laws"])
    assert "safe disabled-state contract" in laws
    assert "not-applicable labels" in laws


def test_gap_ledger_is_explicitly_open_not_fake_complete():
    l=_l()
    assert len(l["records"])==1000
    assert l["summary"]["open"]==1000
    assert l["summary"]["signed_current"]==0
    assert l["summary"]["essentials_1000_qualified"] is False
    assert all(r["state"]=="open" for r in l["records"])
    assert all(r["implementation_identity"] is None for r in l["records"])
    assert all(r["closure_receipt_digest"] is None for r in l["records"])

def test_waivers_and_not_applicable_cannot_close_essentials():
    c=_c()
    assert c["exception_policy"]["waivers_can_mark_complete"] is False
    assert c["exception_policy"]["exception_can_bypass_non_compensable_invariant"] is False
    assert c["applicability"]["not_applicable_completion"] is False

def test_stale_evidence_must_reopen_and_propagate():
    c=_c()
    assert "moves the affected essential out of signed closure" in c["freshness"]["revalidation_rule"]
    assert "invalidates downstream ESS levels" in c["freshness"]["dependency_propagation"]
    assert "mapped implementation changes" in c["freshness"]["invalidation_triggers"]
    assert "new failing regression evidence" in c["freshness"]["invalidation_triggers"]

def test_signatures_are_separated_and_finality_cannot_self_attest():
    c=_c()
    assert "distinct identities" in c["signatures"]["separation_rule"]
    assert "whole-system finality verifier" in c["signatures"]["finality_rule"]
    assert c["finality"]["no_majority_vote"] is True
    assert c["finality"]["no_score_substitution"] is True
    assert c["finality"]["no_benchmark_substitution"] is True

def test_ledger_divergence_is_detected():
    m=_m(); d=_d(); l=_l()
    l["records"][0]["state"]="signed_current"
    l["records"][0]["implementation_identity"]="fake"
    l["records"][0]["closure_receipt_digest"]="fake"
    l["records"][0]["current_evidence_ids"]=["fake"]
    l["summary"]["signed_current"]=1
    l["summary"]["open"]=999
    errors=m.validate(d,_s(),_c(),l)
    assert any("signed-current count diverges" in e for e in errors)


def test_dependency_topology_parallelizes_domains_and_fans_in_finality():
    d=_d()
    levels=d["levels"]
    for i,l in enumerate(levels,1):
        stratum=((i-1)//10)+1
        stage=((i-1)%10)+1
        if stratum<100:
            expected=[] if stage==1 else [f"ESS1000-{i-1:04d}"]
        elif stage==1:
            expected=[f"ESS1000-{k*10:04d}" for k in range(1,100)]
        else:
            expected=[f"ESS1000-{i-1:04d}"]
        assert l["depends_on"]==expected
    assert d["dependency_topology"]["maximum_parallel_domain_lanes"]==99
    assert d["dependency_topology"]["finality_fan_in"]==99


def test_construction_waves_match_parallel_dependency_topology():
    d=_d()
    waves=d["construction_waves"]
    assert len(waves)==100
    for i,w in enumerate(waves,1):
        assert w["id"]==f"ESS-W{i:03d}"
        assert w["prerequisite_wave"] is None
        if i<100:
            assert w["prerequisite_waves"]==[]
        else:
            assert w["prerequisite_waves"]==[f"ESS-W{k:03d}" for k in range(1,100)]


def test_priority_policy_never_uses_scores_to_cross_severity():
    p=_p()
    assert [x["id"] for x in p["severity_classes"]]==["E0","E1","E2","E3"]
    assert p["hard_order"][-1]=="optional PSI optimization"
    assert "inside the same non-compensable severity class" in p["scoring_within_same_severity"]["rule"]
    assert p["starvation"]["cannot_cross_severity_boundary"] is True
    assert p["batching"]["max_parallel_lanes"]==99

def test_execution_frontier_starts_with_99_parallel_open_lanes():
    f=_f()
    assert len(f["lanes"])==99
    assert f["execution_model"]["parallel_domain_lanes"]==99
    assert f["snapshot"]["open"]==1000
    assert f["snapshot"]["signed_current"]==0
    assert all(l["state"]=="open" for l in f["lanes"])
    assert all(l["active_severity"] is None for l in f["lanes"])
    assert all(l["planning_default_severity"]!="E0" for l in f["lanes"])

def test_execution_finality_lane_requires_all_99_domain_closure_gates():
    f=_f()
    gates=[f"ESS1000-{i*10:04d}" for i in range(1,100)]
    assert f["execution_model"]["finality_gate_inputs"]==gates
    final=f["finality_lane"]
    assert final["state"]=="blocked"
    assert final["blocked_by"]==gates
    assert final["current_frontier"] is None
