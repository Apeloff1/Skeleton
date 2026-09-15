"""Tests for policy versioning, rollback, and inheritance.

Covers version CRUD, lineage, diff, rollback, and cross-surface
inheritance with override propagation.
"""
from __future__ import annotations

import pytest

from skeleton.organism.policy_versioning import (
    diff_versions,
    get_version,
    inherit_version,
    list_versions,
    rollback,
    save_version,
    version_card,
    version_lineage,
)
from skeleton.organism.policy_rollback_control import (
    rollback_by_surface,
    rollback_control_card,
    rollback_preview,
)
from skeleton.organism.policy_state import load_policy, save_policy


class TestPolicyVersioning:
    def test_save_version(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        vid = save_version(comment="test", author="pytest", root=tmp_path)
        assert vid.startswith("pv-")

    def test_list_versions(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        save_version(comment="v1", root=tmp_path)
        save_version(comment="v2", root=tmp_path)
        versions = list_versions(root=tmp_path)
        assert len(versions) >= 2

    def test_get_version(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        vid = save_version(comment="get test", root=tmp_path)
        v = get_version(vid, root=tmp_path)
        assert v is not None
        assert v["comment"] == "get test"

    def test_rollback(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        vid = save_version(comment="rollback source", root=tmp_path)
        # Change policy
        policy["quality_thresholds"]["forge"] = 0.9
        save_policy(policy, root=tmp_path)
        result = rollback(vid, root=tmp_path)
        assert result["kind"] == "policy-rollback"
        assert result["ok"] == 1
        current = load_policy(root=tmp_path)
        assert current["quality_thresholds"]["forge"] == 0.7

    def test_diff_versions(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        v1 = save_version(comment="diff a", root=tmp_path)
        policy["quality_thresholds"]["forge"] = 0.9
        save_policy(policy, root=tmp_path)
        v2 = save_version(comment="diff b", root=tmp_path)
        diff = diff_versions(v1, v2, root=tmp_path)
        assert diff["ok"] == 1
        assert "quality_thresholds" in diff["changed_keys"]

    def test_version_lineage(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        v1 = save_version(comment="ancestor", root=tmp_path)
        v2 = save_version(comment="child", parent_id=v1, root=tmp_path)
        lineage = version_lineage(v2, root=tmp_path)
        assert v2 in lineage
        assert v1 in lineage

    def test_inherit_version(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7, "plan": 0.8}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        parent_vid = save_version(comment="parent", root=tmp_path)
        child_vid = inherit_version(
            parent_vid,
            child_surfaces=["forge"],
            overrides={"quality_thresholds": {"forge": 0.5}},
            root=tmp_path,
        )
        assert child_vid.startswith("pv-")
        child = get_version(child_vid, root=tmp_path)
        assert child["policy_snapshot"]["quality_thresholds"]["forge"] == 0.5
        assert child["policy_snapshot"]["quality_thresholds"]["plan"] == 0.8

    def test_version_card(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        save_version(comment="card test", root=tmp_path)
        card = version_card(root=tmp_path)
        assert card["kind"] == "policy-version-card"
        assert card["total_versions"] >= 1


class TestRollbackControl:
    def test_rollback_control_card(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        save_version(comment="rc test", root=tmp_path)
        card = rollback_control_card(root=tmp_path)
        assert card["kind"] == "rollback-control-card"
        assert "actions" in card

    def test_rollback_by_surface(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7, "plan": 0.8}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        save_version(comment="surface test", surfaces=["forge"], root=tmp_path)
        policy["quality_thresholds"]["forge"] = 0.9
        save_policy(policy, root=tmp_path)
        result = rollback_by_surface("forge", root=tmp_path)
        assert result["kind"] == "policy-rollback"

    def test_rollback_preview(self, tmp_path):
        policy = {"quality_thresholds": {"forge": 0.7}, "repair_enabled": {}, "repair_classes": {}}
        save_policy(policy, root=tmp_path)
        vid = save_version(comment="preview test", root=tmp_path)
        policy["quality_thresholds"]["forge"] = 0.9
        save_policy(policy, root=tmp_path)
        preview = rollback_preview(vid, root=tmp_path)
        assert preview["kind"] == "rollback-preview"
        assert preview["ok"] == 1
        assert "quality_thresholds" in preview["changes"]
