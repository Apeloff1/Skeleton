"""Upstream ownership refinement reconciled with canonical namespace migrations."""
from pathlib import Path
import json
from skeleton.repo_machine.config import load_machine_config
from skeleton.repo_machine.atlas import placement_for_path

ROOT = Path(__file__).resolve().parents[1]


def test_simulation_zone_only_owns_actual_simulation_surfaces():
    config = load_machine_config(ROOT)
    simulation = next(zone for zone in config.zones if zone.name == "simulation")
    assert set(simulation.prefixes) == {"skeleton/simulation/", "godot.pointer"}


def test_legacy_roots_do_not_reclaim_canonical_runtime_ownership():
    config = load_machine_config(ROOT)
    for legacy, canonical, owner in (
        ("skeleton/galaxy/core.py", "skeleton/distributed/galaxy/core.py", "distributed-runtime"),
        ("skeleton/social/graph.py", "skeleton/research/social/graph.py", "research-evidence"),
        ("skeleton/era/bind.py", "skeleton/simulation/era/bind.py", "simulation-runtime"),
    ):
        old = placement_for_path(config, legacy)
        current = placement_for_path(config, canonical)
        assert old.lifecycle == "transitional"
        assert current.lifecycle == "canonical"
        assert old.owner == current.owner == owner
    organism = placement_for_path(config, "skeleton/organism/engine.py")
    assert (organism.zone, organism.owner, organism.lifecycle) == ("organism-runtime", "core-runtime", "support")


def test_refinement_retains_source_identity_without_batch_id_collision():
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    ids = [batch["id"] for batch in plan["batches"]]
    assert len(ids) == len(set(ids))
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-041")
    assert batch["mode"] == "taxonomy-classification"
    assert batch["state"] == "classified"
    assert batch["source_batch_id"] == "TREE-033"
    assert batch["source_commit"] == "f5e19db27aceaa22224b9dce247eecd2cb30d0f6"
    assert next(item for item in plan["batches"] if item["id"] == "TREE-033")["destination"] == "skeleton/simulation/era/"


def test_zone_prefixes_do_not_silently_shadow_duplicate_owners():
    config = load_machine_config(ROOT)
    prefixes = [prefix for zone in config.zones for prefix in zone.prefixes]
    assert len(prefixes) == len(set(prefixes))
