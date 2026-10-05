"""Policy state tests."""
from __future__ import annotations

from skeleton.organism.policy_state import load_policy, set_repair_class, set_repair_enabled, set_threshold
from skeleton.organism.policy_card import policy_card


def test_policy_defaults_load(tmp_path):
    policy = load_policy(root=tmp_path)
    assert policy["quality_thresholds"]["forge"] == 0.7
    assert policy["repair_enabled"]["plan"] is True


def test_policy_threshold_update(tmp_path):
    policy = set_threshold("forge", 0.82, root=tmp_path)
    assert policy["quality_thresholds"]["forge"] == 0.82


def test_policy_repair_toggle_update(tmp_path):
    policy = set_repair_enabled("npc", False, root=tmp_path)
    assert policy["repair_enabled"]["npc"] is False


def test_policy_repair_class_update(tmp_path):
    policy = set_repair_class("scene_stub", False, root=tmp_path)
    assert policy["repair_classes"]["scene_stub"] is False


def test_policy_card_exposes_state(tmp_path):
    set_threshold("dialogue", 0.9, root=tmp_path)
    card = policy_card(root=tmp_path)
    assert card["kind"] == "policy-card"
    assert card["thresholds"]["dialogue"] == 0.9
