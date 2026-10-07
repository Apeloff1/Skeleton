"""Regression coverage for TREE-036 distributed-network migration."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_network_package_reexports_canonical_distributed_surface() -> None:
    legacy = importlib.import_module("skeleton.network")
    canonical = importlib.import_module("skeleton.distributed.network")

    assert legacy.ModelPlacementDecision is canonical.ModelPlacementDecision
    assert legacy.RemoteExecutionRequest is canonical.RemoteExecutionRequest
    assert legacy.Replica is canonical.Replica


def test_canonical_and_ai_network_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/distributed/network", "skeleton/ai/runtime/distributed/network"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.network" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_retargets_network_to_canonical_distributed_owner() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    network = next(item for item in manifest["mappings"] if item["id"] == "AIFT-NETWORK")

    assert network["source"] == "skeleton/distributed/network"
    assert network["destination"] == "skeleton/ai/runtime/distributed/network"
    tree = subprocess.check_output(["git", "write-tree"], cwd=ROOT, text=True).strip()
    assert network["source_git_object_sha"] == subprocess.check_output(
        ["git", "rev-parse", f"{tree}:skeleton/distributed/network"], cwd=ROOT, text=True
    ).strip()


def test_network_migration_follows_galaxy_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    sources = [item["source"] for item in plan["batches"]]
    assert sources.index("skeleton/galaxy/") < sources.index("skeleton/network/")
    batch = next(item for item in plan["batches"] if item["source"] == "skeleton/network/")
    assert batch["state"] == "canonicalized"
