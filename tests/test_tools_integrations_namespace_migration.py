"""Regression coverage for TREE-037 tools-integrations migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_integrations_package_reexports_canonical_tools_surface() -> None:
    legacy = importlib.import_module("skeleton.integrations")
    canonical = importlib.import_module("skeleton.tools.integrations")

    assert legacy.ConnectorRegistry is canonical.ConnectorRegistry
    assert legacy.WebhookHandler is canonical.WebhookHandler
    assert legacy.APICredentials is canonical.APICredentials


def test_canonical_and_ai_integrations_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/tools/integrations", "skeleton/ai/runtime/tools/integrations"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.integrations" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_governs_tools_parent_and_integrations_child() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    tools = next(item for item in manifest["mappings"] if item["id"] == "AIFT-TOOLS")
    integrations = next(item for item in manifest["mappings"] if item["id"] == "AIFT-INTEGRATIONS")

    assert tools["source"] == "skeleton/tools"
    assert tools["destination"] == "skeleton/ai/runtime/tools"
    assert tools["source_git_object_sha"] == "63239f151af1b31b36db84ead936f9557aa62fb1"
    assert tools["overlay_children"] == ["integrations"]
    assert integrations["source"] == "skeleton/tools/integrations"
    assert integrations["destination"] == "skeleton/ai/runtime/tools/integrations"
    assert integrations["source_git_object_sha"] == "7a342bbbcfac4bd26124df1c96bbf86df1b183d7"
    assert "skeleton/tools" not in manifest["planned_path_audit"]["planned_but_absent"]


def test_integrations_migration_follows_provenance_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    ids = [item["id"] for item in plan["batches"]]
    assert ids[-2:] == ["TREE-036", "TREE-037"]
