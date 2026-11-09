"""Tests for policy inheritance and versioning."""
from __future__ import annotations

import pytest

from skeleton.organism.policy_inheritance import (
    break_inheritance,
    inheritance_card,
    load_inheritance,
    resolve_policy,
    resolve_repair_enabled,
    resolve_threshold,
    save_inheritance,
    set_parent,
)
from skeleton.organism.policy_state import load_policy, save_policy, set_repair_enabled, set_threshold
from skeleton.organism.policy_versions import (
    auto_version_on_change,
    diff_versions,
    load_versions,
    record_version,
    rollback_to_version,
    version_card,
)


class TestPolicyInheritance:
    def test_default_inheritance(self, tmp_path):
        mapping = load_inheritance(root=tmp_path)
        assert "forge" in mapping
        assert mapping["forge"] == "global"

    def test_set_parent(self, tmp_path):
        # Set up parent surface
        set_threshold("parent_surf", 0.8, root=tmp_path)
        result = set_parent("child_surf", "parent_surf", root=tmp_path)
        assert result["kind"] == "inheritance-set"
        assert result["child"] == "child_surf"
        assert result["parent"] == "parent_surf"

    def test_resolve_threshold_direct(self, tmp_path):
        set_threshold("forge", 0.82, root=tmp_path)
        thresh = resolve_threshold("forge", root=tmp_path)
        assert thresh == 0.82

    def test_resolve_threshold_inherited(self, tmp_path):
        set_threshold("parent", 0.9, root=tmp_path)
        save_inheritance({"child": "parent"}, root=tmp_path)
        thresh = resolve_threshold("child", root=tmp_path)
        assert thresh == 0.9

    def test_resolve_threshold_chain(self, tmp_path):
        set_threshold("grandparent", 0.75, root=tmp_path)
        save_inheritance({"parent": "grandparent", "child": "parent"}, root=tmp_path)
        thresh = resolve_threshold("child", root=tmp_path)
        assert thresh == 0.75

    def test_resolve_threshold_fallback(self, tmp_path):
        save_inheritance({}, root=tmp_path)
        thresh = resolve_threshold("unknown", root=tmp_path, fallback=0.6)
        assert thresh == 0.6

    def test_resolve_repair_enabled(self, tmp_path):
        set_repair_enabled("forge", False, root=tmp_path)
        enabled = resolve_repair_enabled("forge", root=tmp_path)
        assert enabled is False

    def test_resolve_repair_enabled_inherited(self, tmp_path):
        set_repair_enabled("parent", False, root=tmp_path)
        save_inheritance({"child": "parent"}, root=tmp_path)
        enabled = resolve_repair_enabled("child", root=tmp_path)
        assert enabled is False

    def test_resolve_policy(self, tmp_path):
        set_threshold("forge", 0.8, root=tmp_path)
        set_repair_enabled("forge", True, root=tmp_path)
        policy = resolve_policy("forge", root=tmp_path)
        assert policy["threshold"] == 0.8
        assert policy["repair_enabled"] is True

    def test_inheritance_card(self, tmp_path):
        set_threshold("forge", 0.8, root=tmp_path)
        card = inheritance_card(root=tmp_path)
        assert card["kind"] == "inheritance-card"
        assert "forge" in card["tree"]

    def test_break_inheritance(self, tmp_path):
        set_threshold("parent", 0.9, root=tmp_path)
        save_inheritance({"child": "parent"}, root=tmp_path)
        result = break_inheritance("child", root=tmp_path)
        assert result["kind"] == "inheritance-broken"
        assert result["copied_threshold"] == 0.9
        # Now child should have its own value
        policy = load_policy(root=tmp_path)
        assert "child" in policy["quality_thresholds"]

    def test_unknown_parent_error(self, tmp_path):
        result = set_parent("child", "nonexistent", root=tmp_path)
        assert result["kind"] == "inheritance-error"


class TestPolicyVersions:
    def test_record_and_load_version(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        result = record_version(policy, root=tmp_path, note="test")
        assert result["kind"] == "version-recorded"
        assert result["note"] == "test"

        versions = load_versions(root=tmp_path)
        assert len(versions) == 1
        assert versions[0]["note"] == "test"

    def test_version_card(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        record_version(policy, root=tmp_path)
        card = version_card(root=tmp_path)
        assert card["kind"] == "policy-version-card"
        assert card["version_count"] == 1

    def test_rollback(self, tmp_path):
        # Record version 1
        policy1 = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        record_version(policy1, root=tmp_path)

        # Change policy
        policy2 = {"quality_thresholds": {"forge": 0.9}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy2, root=tmp_path)
        record_version(policy2, root=tmp_path)

        # Rollback to first version
        result = rollback_to_version(0, root=tmp_path)
        assert result["kind"] == "rollback-applied"

        # Verify policy was restored
        current = load_policy(root=tmp_path)
        assert current["quality_thresholds"]["forge"] == 0.7

    def test_rollback_negative_index(self, tmp_path):
        policy1 = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        record_version(policy1, root=tmp_path)
        policy2 = {"quality_thresholds": {"forge": 0.9}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy2, root=tmp_path)
        record_version(policy2, root=tmp_path)

        # Rollback to version -2 (first version)
        result = rollback_to_version(-2, root=tmp_path)
        assert result["kind"] == "rollback-applied"
        current = load_policy(root=tmp_path)
        assert current["quality_thresholds"]["forge"] == 0.7

    def test_rollback_no_versions(self, tmp_path):
        result = rollback_to_version(root=tmp_path)
        assert result["kind"] == "rollback-failed"

    def test_diff_versions(self, tmp_path):
        policy1 = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        record_version(policy1, root=tmp_path)
        policy2 = {"quality_thresholds": {"forge": 0.9}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy2, root=tmp_path)
        record_version(policy2, root=tmp_path)

        diff = diff_versions(-2, -1, root=tmp_path)
        assert diff["kind"] == "policy-diff"
        assert "forge" in diff["threshold_changes"]
        assert diff["threshold_changes"]["forge"]["from"] == 0.7
        assert diff["threshold_changes"]["forge"]["to"] == 0.9

    def test_auto_version_no_change(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        record_version(policy, root=tmp_path)
        result = auto_version_on_change(root=tmp_path)
        assert result["kind"] == "version-no-change"

    def test_auto_version_detects_change(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        record_version(policy, root=tmp_path)

        # Change policy
        policy["quality_thresholds"]["forge"] = 0.9
        save_policy(policy, root=tmp_path)
        result = auto_version_on_change(root=tmp_path)
        assert result["kind"] == "version-recorded"
