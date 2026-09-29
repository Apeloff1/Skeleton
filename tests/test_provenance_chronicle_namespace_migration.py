"""Regression coverage for TREE-036 provenance-chronicle migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_chronicle_package_reexports_canonical_provenance_surface() -> None:
    legacy = importlib.import_module("skeleton.chronicle")
    canonical = importlib.import_module("skeleton.provenance.chronicle")

    assert legacy.ChronicleEngine is canonical.ChronicleEngine
    assert legacy.Helix is canonical.Helix
    assert legacy.capabilities is canonical.capabilities


def test_canonical_and_ai_chronicle_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/provenance/chronicle", "skeleton/ai/runtime/provenance/chronicle"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.chronicle" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_governs_provenance_parent_and_chronicle_child() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    provenance = next(item for item in manifest["mappings"] if item["id"] == "AIFT-PROVENANCE")
    chronicle = next(item for item in manifest["mappings"] if item["id"] == "AIFT-CHRONICLE")

    assert provenance["source"] == "skeleton/provenance"
    assert provenance["destination"] == "skeleton/ai/runtime/provenance"
    assert provenance["source_git_object_sha"] == "0198cb43f5bd16c81f5c8ad333c771d02bdccb60"
    assert provenance["overlay_children"] == ["chronicle"]
    assert chronicle["source"] == "skeleton/provenance/chronicle"
    assert chronicle["destination"] == "skeleton/ai/runtime/provenance/chronicle"
    assert chronicle["source_git_object_sha"] == "5831cc060b6fd0f260437150b172796da8318e43"
    assert "skeleton/provenance" not in manifest["planned_path_audit"]["planned_but_absent"]


def test_chronicle_migration_follows_knowledge_graphs_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    ids = [item["id"] for item in plan["batches"]]
    assert ids[-2:] == ["TREE-035", "TREE-036"]
