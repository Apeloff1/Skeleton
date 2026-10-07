from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "machine" / "project_self_improvement_1000.json"
EPOCH = ROOT / "machine" / "project_self_improvement_epoch_contract.json"
SCHEDULER = ROOT / "machine" / "project_self_improvement_idle_scheduler.json"
MODULE = ROOT / "scripts" / "check_project_self_improvement_1000.py"

def _module():
    spec = importlib.util.spec_from_file_location("check_project_self_improvement_1000", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _data():
    return json.loads(DATA.read_text(encoding="utf-8"))

def _epoch():
    return json.loads(EPOCH.read_text(encoding="utf-8"))

def _scheduler():
    return json.loads(SCHEDULER.read_text(encoding="utf-8"))

def test_contract_epoch_and_scheduler_are_jointly_valid():
    assert _module().validate(_data(), _epoch(), _scheduler()) == []

def test_exact_1000_level_identity_and_100_strata():
    d = _data()
    assert [x["id"] for x in d["levels"]] == [f"PSI1000-{i:04d}" for i in range(1, 1001)]
    assert len(d["strata"]) == 100
    assert len(d["construction_waves"]) == 100

def test_every_level_is_project_scoped_idle_eligible_and_preemptible():
    for level in _data()["levels"]:
        assert level["project_scoped"] is True
        assert level["idle_eligible"] is True
        assert level["foreground_preemptible"] is True
        assert level["production_mutation_allowed"] is False

def test_idle_activation_is_immediate_and_foreground_has_absolute_priority():
    d = _data()
    idle = d["idle_activation"]
    resources = d["resource_governance"]
    assert idle["semantics"] == "foreground-idle, not machine-idle"
    assert idle["activation"] == "immediate when deterministic idle predicate becomes true"
    assert "immediately" in idle["preemption"]
    assert resources["foreground_priority"] == "absolute"
    assert resources["cancellation_required"] is True
    assert resources["no_unbounded_loop"] is True

def test_epoch_fails_closed_if_idle_state_is_unknown():
    e = _epoch()
    assert e["initial_state"] == "foreground_active"
    assert e["idle_predicate"]["false_on_unknown"] is True
    first = e["transitions"][0]
    assert first == {
        "from": "foreground_active",
        "to": "idle_eligible",
        "guard": "idle_predicate_true",
    }

def test_epoch_preemption_covers_every_active_mirror_state():
    e = _epoch()
    p = e["global_preemption_transitions"]
    assert p["to"] == "preempted"
    assert set(p["source_states"]) == {
        "idle_eligible","baseline_freezing","mirror_gap_mining","candidate_synthesis",
        "adversarial_challenge","sandbox_experiment","causal_evaluation",
        "learning_consolidation","promotion_pending",
    }
    assert "foreground_instruction_arrived" in p["guards"]
    assert "protected_resource_reservation_violated" in p["guards"]
    assert "never partially promote" in p["action"]

def test_mirror_room_has_proposer_challenger_role_reversal_verifier_archivist():
    m = _data()["mirror_room_topology"]
    for key in ("proposer_room","challenger_room","role_reversal","verifier_room","archivist_plane","isolation","finality"):
        assert m[key]

def test_mirror_rooms_cannot_be_promotion_authority():
    e = _epoch()
    forbidden = set(e["promotion_receipt_schema"]["forbidden_authority"])
    assert forbidden == {"proposer_room","challenger_room","verifier_room"}

def test_project_completion_does_not_leak_between_projects():
    d = _data()
    inst = d["project_instantiation"]
    assert "independently for every project" in inst["rule"]
    assert "deny-by-default" in inst["cross_project_transfer"]
    assert d["per_project_completion_schema"]["key"] == "project_id"
    assert "no project can satisfy another project's PSI-1000 maturity" in _epoch()["invariants"]

def test_self_improvement_uses_candidates_not_silent_production_mutation():
    c = _data()["candidate_policy"]
    assert c["production_in_place_self_mutation"] is False
    assert c["immutable_baseline_required"] is True
    assert c["versioned_candidates_required"] is True
    assert "weight_candidate" in c["candidate_types"]
    assert "code_patch" in c["candidate_types"]
    assert "rollback or compensation path" in c["promotion_requires"]
    assert _epoch()["locks"]["candidate_namespace_lock"]["production_write"] is False

def test_each_epoch_is_bounded_and_non_carrying():
    e = _epoch()
    required = set(e["epoch_budget_schema"]["required"])
    assert {"wall_clock_limit","experiment_limit","model_compute_limit","cpu_limit","memory_limit",
            "storage_limit","network_limit","external_api_limit"} <= required
    assert e["epoch_budget_schema"]["carryover"] == "none unless explicitly reauthorized by next epoch"
    assert "every epoch terminates before another epoch begins for the same project" in e["invariants"]

def test_all_learning_links_remain_inside_learning_400_and_adversarial_400():
    d = _data()
    for i, level in enumerate(d["levels"], start=1):
        n = ((i - 1) % 400) + 1
        assert level["linked_learning_layer"] == f"L400-{n:03d}"
        assert level["linked_adversarial_layer"] == f"A400-{n:03d}"

def test_idle_scheduler_prefers_gain_but_preserves_exploration_and_preemption():
    sch = _scheduler()
    assert "expected_capability_gain" in sch["ranking"]["maximize"]
    assert "expected_risk_reduction" in sch["ranking"]["maximize"]
    assert sch["portfolio_policy"]["exploration_share_floor"] >= 0.20
    assert sch["portfolio_policy"]["domain_starvation_limit_epochs"] > 0
    assert sch["project_fairness"]["starvation_forbidden"] is True
    assert sch["dispatch"]["foreground_preemption"] == "absolute"
    assert sch["dispatch"]["one_active_epoch_per_project"] is True

def test_scheduler_backs_off_dead_ends_and_quarantines_repeated_failures():
    p = _scheduler()["plateau_policy"]
    assert p["no_gain_threshold"] == 3
    assert p["repeated_failure_threshold"] == 5
    assert "exponential backoff" in p["action_after_no_gain"]
    assert "quarantine" in p["action_after_repeated_failure"]

def test_template_starts_unsigned():
    d = _data()
    assert d["completion"]["template_signed_complete"] == 0
    assert d["completion"]["implementation_claim"] is False
    assert d["completion"]["global_project_qualification_claim"] is False
    assert all(not x["complete"] for x in d["levels"])
