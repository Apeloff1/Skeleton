"""Regression coverage for TREE-035 distributed-galaxy migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from skeleton.app.runtime import get_capability

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_galaxy_package_reexports_canonical_distributed_surface() -> None:
    legacy = importlib.import_module("skeleton.galaxy")
    canonical = importlib.import_module("skeleton.distributed.galaxy")

    assert legacy.NodeTransport is canonical.NodeTransport
    assert legacy.ConsensusEngine is canonical.ConsensusEngine
    assert legacy.GalaxyBridge is canonical.GalaxyBridge
    assert legacy.FleetCoordinator is canonical.FleetCoordinator


def test_canonical_and_ai_galaxy_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/distributed/galaxy", "skeleton/ai/runtime/distributed/galaxy"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.galaxy" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_and_capability_loader_follow_canonical_galaxy_owner() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    galaxy = next(item for item in manifest["mappings"] if item["id"] == "AIFT-GALAXY")

    assert galaxy["source"] == "skeleton/distributed/galaxy"
    assert galaxy["destination"] == "skeleton/ai/runtime/distributed/galaxy"
    assert galaxy["source_git_object_sha"] == "4edf8f5dbd7323a5581072a3430b1ad85c81f2dd"
    assert get_capability("galaxy").module == "skeleton.distributed.galaxy"
    assert "skeleton/distributed" not in manifest["planned_path_audit"]["planned_but_absent"]


def test_galaxy_migration_follows_social_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    sources = [item["source"] for item in plan["batches"]]
    assert sources.index("skeleton/social/") < sources.index("skeleton/galaxy/")
    batch = next(item for item in plan["batches"] if item["source"] == "skeleton/galaxy/")
    assert batch["state"] == "canonicalized"
