"""Regression coverage for TREE-038 knowledge-graphs migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_graphs_package_reexports_canonical_knowledge_surface() -> None:
    legacy = importlib.import_module("skeleton.graphs")
    canonical = importlib.import_module("skeleton.knowledge.graphs")

    assert legacy.GraphEngine is canonical.GraphEngine
    assert legacy.graph_card is canonical.graph_card
    assert legacy.capabilities is canonical.capabilities


def test_canonical_and_ai_graph_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/knowledge/graphs", "skeleton/ai/runtime/knowledge/graphs"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.graphs" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_governs_knowledge_parent_and_graph_child() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    knowledge = next(item for item in manifest["mappings"] if item["id"] == "AIFT-KNOWLEDGE")
    graphs = next(item for item in manifest["mappings"] if item["id"] == "AIFT-GRAPHS")

    assert knowledge["source"] == "skeleton/knowledge"
    assert knowledge["destination"] == "skeleton/ai/runtime/knowledge"
    assert knowledge["source_git_object_sha"] == "518f871ec380c08d8226adbfb0122493efd85d13"
    assert knowledge["overlay_children"] == ["graphs"]
    assert graphs["source"] == "skeleton/knowledge/graphs"
    assert graphs["destination"] == "skeleton/ai/runtime/knowledge/graphs"
    assert graphs["source_git_object_sha"] == "5a5b5627f3b15e783798900eaa8758eaccfee94f"
    assert "skeleton/knowledge" not in manifest["planned_path_audit"]["planned_but_absent"]


def test_graph_migration_follows_distributed_mesh_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    sources = [item["source"] for item in plan["batches"]]
    assert sources.index("skeleton/mesh/") < sources.index("skeleton/graphs/")
    batch = next(item for item in plan["batches"] if item["source"] == "skeleton/graphs/")
    assert batch["state"] == "canonicalized"
