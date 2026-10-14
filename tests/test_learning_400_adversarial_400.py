from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "machine" / "learning_400_adversarial_400.json"
MODULE = ROOT / "scripts" / "check_learning_400_adversarial_400.py"

def _load():
    spec = importlib.util.spec_from_file_location("check_learning_400_adversarial_400", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def _data():
    return json.loads(DATA.read_text(encoding="utf-8"))

def test_contract_is_valid():
    assert _load().validate(_data()) == []

def test_exact_identity_spaces_and_pairs():
    d = _data()
    assert [x["id"] for x in d["learning_layers"]] == [f"L400-{i:03d}" for i in range(1, 401)]
    assert [x["id"] for x in d["adversarial_layers"]] == [f"A400-{i:03d}" for i in range(1, 401)]
    assert len(d["learning_strata"]) == 40
    assert len(d["adversarial_strata"]) == 40
    for i, (l, a) in enumerate(zip(d["learning_layers"], d["adversarial_layers"]), start=1):
        assert l["paired_adversarial_layer"] == f"A400-{i:03d}"
        assert a["paired_learning_layer"] == f"L400-{i:03d}"

def test_starts_unsigned_without_false_completion():
    d = _data()
    c = d["completion"]
    assert c["learning_signed_complete"] == 0
    assert c["adversarial_signed_complete"] == 0
    assert c["paired_system_qualified"] is False
    assert all(not x["complete"] for x in d["learning_layers"])
    assert all(not x["complete"] for x in d["adversarial_layers"])

def test_web_video_reading_project_and_weight_capabilities_are_explicit():
    d = _data()
    names = {x["stratum"]: x["scope"] for x in d["learning_layers"][::10]}
    assert "Open-Web Discovery & Crawl Planning" in names
    assert "Web Acquisition & Dynamic Content" in names
    assert "Reading & Document Understanding" in names
    assert "Video & Audio Learning" in names
    assert "Project-Derived Learning" in names
    assert "Weight Genesis & Native Pretraining" in names
    assert "Continual & Online Learning" in names
    assert "Wisdom, Judgment & Long-Horizon Learning" in names

def test_web_acquisition_is_powerful_but_policy_bound():
    p = _data()["acquisition_policy"]
    assert p["public_web"] is True
    assert p["rendered_dynamic_content"] is True
    assert p["video_audio_understanding"] is True
    assert p["authentication_bypass"] is False
    assert p["paywall_bypass"] is False
    assert p["anti_bot_evasion"] is False
    assert p["source_provenance_required"] is True

def test_native_weight_creation_and_project_learning_are_candidate_gated():
    w = _data()["weight_policy"]
    assert w["native_weight_creation"] is True
    assert w["native_pretraining"] is True
    assert w["project_specific_adapters"] is True
    assert w["continual_candidate_learning"] is True
    assert w["weight_editing_and_merging"] is True
    assert w["production_in_place_self_mutation"] is False

def test_learning_completion_fails_if_paired_adversary_is_incomplete():
    module = _load()
    d = _data()
    l = d["learning_layers"][0]
    l["maturity"] = "signed_complete"
    l["implementation_signed"] = True
    l["independent_verification_signed"] = True
    l["complete"] = True
    l["evidence"] = ["exact-head:test"]
    d["completion"]["learning_signed_complete"] = 1
    errors = module.validate(d)
    assert any("paired A400-001 is incomplete" in e for e in errors)
