"""Regression coverage for TREE-039 provenance-chronicle migration."""

from __future__ import annotations

import importlib
import json
import subprocess
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
    tree = subprocess.check_output(["git", "write-tree"], cwd=ROOT, text=True).strip()
    assert provenance["source_git_object_sha"] == subprocess.check_output(
        ["git", "rev-parse", f'{tree}:{provenance["source"]}'], cwd=ROOT, text=True
    ).strip()
    assert provenance["overlay_children"] == ["chronicle"]
    assert chronicle["source"] == "skeleton/provenance/chronicle"
    assert chronicle["destination"] == "skeleton/ai/runtime/provenance/chronicle"
    tree = subprocess.check_output(["git", "write-tree"], cwd=ROOT, text=True).strip()
    assert chronicle["source_git_object_sha"] == subprocess.check_output(
        ["git", "rev-parse", f'{tree}:{chronicle["source"]}'], cwd=ROOT, text=True
    ).strip()
    assert "skeleton/provenance" not in manifest["planned_path_audit"]["planned_but_absent"]


def test_chronicle_migration_follows_knowledge_graphs_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    sources = [item["source"] for item in plan["batches"]]
    assert sources.index("skeleton/graphs/") < sources.index("skeleton/chronicle/")
    batch = next(item for item in plan["batches"] if item["source"] == "skeleton/chronicle/")
    assert batch["state"] == "canonicalized"
