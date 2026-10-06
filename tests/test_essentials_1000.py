from __future__ import annotations
import importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"machine"/"essentials_1000.json"
SCHED=ROOT/"machine"/"project_self_improvement_idle_scheduler.json"
MODULE=ROOT/"scripts"/"check_essentials_1000.py"

def _m():
    spec=importlib.util.spec_from_file_location("check_essentials_1000",MODULE)
    assert spec and spec.loader
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
def _d(): return json.loads(DATA.read_text(encoding="utf-8"))
def _s(): return json.loads(SCHED.read_text(encoding="utf-8"))

def test_contract_is_valid(): assert _m().validate(_d(),_s())==[]
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
