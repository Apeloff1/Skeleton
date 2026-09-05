"""Tests for policy versioning and rollback control."""
from __future__ import annotations

import pytest

from skeleton.organism.policy_rollback_control import (
    rollback_by_surface,
    rollback_control_card,
    rollback_preview,
)
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
from skeleton.organism.policy_state import default_policy, load_policy, save_policy


class TestSaveVersion:
    def test_save_and_list(self, tmp_path):
        policy = default_policy()
        vid = save_version(policy, comment="test", author="pytest", root=tmp_path)
        assert vid.startswith("pv-")
        versions = list_versions(root=tmp_path)
        assert len(versions) >= 1
        assert versions[0]["comment"] == "test"
        assert versions[0]["author"] == "pytest"

    def test_get_version(self, tmp_path):
        policy = default_policy()
        vid = save_version(policy, comment="test", root=tmp_path)
        v = get_version(vid, root=tmp_path)
        assert v is not None
        assert v["version_id"] == vid

    def test_get_version_missing(self, tmp_path):
        assert get_version("pv-nonexistent", root=tmp_path) is None


class TestRollback:
    def test_rollback_success(self, tmp_path):
        policy1 = default_policy()
        policy1["quality_thresholds"]["forge"] = 0.5
        vid1 = save_version(policy1, comment="low", root=tmp_path)

        policy2 = default_policy()
        policy2["quality_thresholds"]["forge"] = 0.9
        save_policy(policy2, root=tmp_path)

        result = rollback(vid1, root=tmp_path)
        assert result["kind"] == "policy-rollback"
        assert result["ok"] == 1
        assert result["version_id"] == vid1

        current = load_policy(root=tmp_path)
        assert current["quality_thresholds"]["forge"] == 0.5

    def test_rollback_not_found(self, tmp_path):
        result = rollback("pv-nonexistent", root=tmp_path)
        assert result["ok"] == 0
        assert result["reason"] == "version-not-found"


class TestDiffVersions:
    def test_diff(self, tmp_path):
        policy = default_policy()
        vid1 = save_version(policy, comment="v1", root=tmp_path)
        policy["quality_thresholds"]["forge"] = 0.99
        vid2 = save_version(policy, comment="v2", root=tmp_path)

        diff = diff_versions(vid1, vid2, root=tmp_path)
        assert diff["ok"] == 1
        assert "quality_thresholds" in diff["changed_keys"]
        assert diff["changes"]["quality_thresholds"]["before"]["forge"] == 0.7
        assert diff["changes"]["quality_thresholds"]["after"]["forge"] == 0.99


class TestVersionLineage:
    def test_lineage(self, tmp_path):
        policy = default_policy()
        vid1 = save_version(policy, comment="root", root=tmp_path)
        vid2 = save_version(policy, parent_id=vid1, comment="child", root=tmp_path)
        lineage = version_lineage(vid2, root=tmp_path)
        assert lineage[0] == vid2
        assert lineage[1] == vid1


class TestInheritVersion:
    def test_inherit(self, tmp_path):
        policy = default_policy()
        vid = save_version(policy, comment="parent", root=tmp_path)
        child_vid = inherit_version(
            vid,
            child_surfaces=["forge"],
            overrides={"quality_thresholds": {"forge": 0.3}},
            root=tmp_path,
        )
        assert child_vid.startswith("pv-")
        child = get_version(child_vid, root=tmp_path)
        assert child["parent_id"] == vid
        assert child["policy_snapshot"]["quality_thresholds"]["forge"] == 0.3


class TestVersionCard:
    def test_card(self, tmp_path):
        policy = default_policy()
        save_version(policy, comment="v1", root=tmp_path)
        card = version_card(root=tmp_path)
        assert card["kind"] == "policy-version-card"
        assert card["total_versions"] >= 1


class TestRollbackControlCard:
    def test_card(self, tmp_path):
        policy = default_policy()
        save_version(policy, comment="v1", root=tmp_path)
        save_version(policy, comment="v2", root=tmp_path)
        card = rollback_control_card(root=tmp_path)
        assert card["kind"] == "rollback-control-card"
        assert card["version_count"] >= 2
        assert len(card["actions"]) >= 2

    def test_card_empty(self, tmp_path):
        card = rollback_control_card(root=tmp_path)
        assert card["version_count"] == 0


class TestRollbackBySurface:
    def test_surface_rollback(self, tmp_path):
        policy = default_policy()
        save_version(policy, surfaces=["forge"], comment="forge-v1", root=tmp_path)
        policy["quality_thresholds"]["forge"] = 0.99
        save_policy(policy, root=tmp_path)

        result = rollback_by_surface("forge", root=tmp_path)
        assert result["ok"] == 1
        assert result["surface"] == "forge"

    def test_surface_rollback_no_versions(self, tmp_path):
        result = rollback_by_surface("forge", root=tmp_path)
        assert result["ok"] == 0
        assert result["reason"] == "no-versions-for-surface"


class TestRollbackPreview:
    def test_preview(self, tmp_path):
        policy = default_policy()
        vid = save_version(policy, comment="v1", root=tmp_path)
        policy["quality_thresholds"]["forge"] = 0.99
        save_policy(policy, root=tmp_path)

        preview = rollback_preview(vid, root=tmp_path)
        assert preview["ok"] == 1
        assert preview["change_count"] >= 1
        assert "quality_thresholds" in preview["changes"]

    def test_preview_not_found(self, tmp_path):
        preview = rollback_preview("pv-nonexistent", root=tmp_path)
        assert preview["ok"] == 0
