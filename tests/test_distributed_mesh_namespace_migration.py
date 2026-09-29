"""Regression coverage for TREE-034 distributed-mesh migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_mesh_modules_reexport_canonical_distributed_surface() -> None:
    legacy_pool = importlib.import_module("skeleton.mesh.connection_pool")
    canonical_pool = importlib.import_module("skeleton.distributed.mesh.connection_pool")
    legacy_capacity = importlib.import_module("skeleton.mesh.capacity_qualification")
    canonical_capacity = importlib.import_module("skeleton.distributed.mesh.capacity_qualification")

    assert legacy_pool.ConnectionPool is canonical_pool.ConnectionPool
    assert legacy_capacity.CapacityQualificationDecision is canonical_capacity.CapacityQualificationDecision


def test_canonical_and_ai_mesh_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/distributed/mesh", "skeleton/ai/runtime/distributed/mesh"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.mesh" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_retargets_mesh_to_canonical_distributed_owner() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    mesh = next(item for item in manifest["mappings"] if item["id"] == "AIFT-MESH")

    assert mesh["source"] == "skeleton/distributed/mesh"
    assert mesh["destination"] == "skeleton/ai/runtime/distributed/mesh"
    assert mesh["source_git_object_sha"] == "73d773eca32320c058c5e1853c9799872538ef62"


def test_mesh_migration_follows_network_wave() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    ids = [item["id"] for item in plan["batches"]]
    assert ids[-2:] == ["TREE-033", "TREE-034"]
