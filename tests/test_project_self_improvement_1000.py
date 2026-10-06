from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "machine" / "project_self_improvement_1000.json"
MODULE = ROOT / "scripts" / "check_project_self_improvement_1000.py"

def _module():
    spec = importlib.util.spec_from_file_location("check_project_self_improvement_1000", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _data():
    return json.loads(DATA.read_text(encoding="utf-8"))

def test_contract_is_valid():
    assert _module().validate(_data()) == []

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

def test_mirror_room_has_proposer_challenger_role_reversal_verifier_archivist():
    m = _data()["mirror_room_topology"]
    for key in ("proposer_room","challenger_room","role_reversal","verifier_room","archivist_plane","isolation","finality"):
        assert m[key]

def test_project_completion_does_not_leak_between_projects():
    d = _data()
    inst = d["project_instantiation"]
    assert "independently for every project" in inst["rule"]
    assert "deny-by-default" in inst["cross_project_transfer"]
    assert d["per_project_completion_schema"]["key"] == "project_id"

def test_self_improvement_uses_candidates_not_silent_production_mutation():
    c = _data()["candidate_policy"]
    assert c["production_in_place_self_mutation"] is False
    assert c["immutable_baseline_required"] is True
    assert c["versioned_candidates_required"] is True
    assert "weight_candidate" in c["candidate_types"]
    assert "code_patch" in c["candidate_types"]
    assert "rollback or compensation path" in c["promotion_requires"]

def test_all_learning_links_remain_inside_learning_400_and_adversarial_400():
    d = _data()
    for i, level in enumerate(d["levels"], start=1):
        n = ((i - 1) % 400) + 1
        assert level["linked_learning_layer"] == f"L400-{n:03d}"
        assert level["linked_adversarial_layer"] == f"A400-{n:03d}"

def test_template_starts_unsigned():
    d = _data()
    assert d["completion"]["template_signed_complete"] == 0
    assert d["completion"]["implementation_claim"] is False
    assert all(not x["complete"] for x in d["levels"])
