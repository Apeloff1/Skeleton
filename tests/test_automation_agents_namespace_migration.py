"""Regression coverage for TREE-028 automation-agent migration."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _python_tree(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*.py"))
    }


def test_legacy_agent_runtime_reexports_canonical_automation_runtime() -> None:
    legacy = importlib.import_module("skeleton.agents.swarm_runtime")
    canonical = importlib.import_module("skeleton.automation.agents.swarm_runtime")
    assert legacy.SwarmRuntime is canonical.SwarmRuntime
    assert legacy.SwarmTask is canonical.SwarmTask


def test_canonical_agent_tree_has_no_legacy_self_imports() -> None:
    root = ROOT / "skeleton" / "automation" / "agents"
    offenders = [
        path.name
        for path in root.glob("*.py")
        if "skeleton.agents" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_canonical_and_ai_agent_trees_are_exact() -> None:
    canonical = ROOT / "skeleton" / "automation" / "agents"
    mirrored = ROOT / "skeleton" / "ai" / "agents" / "core"
    assert _python_tree(canonical) == _python_tree(mirrored)


def test_ai_tree_uses_canonical_automation_sources() -> None:
    manifest = json.loads((ROOT / "machine" / "ai_file_tree.json").read_text(encoding="utf-8"))
    mappings = {item["id"]: item for item in manifest["mappings"]}
    assert mappings["AIFT-AGENTS"]["source"] == "skeleton/automation/agents"
    assert mappings["AIFT-SWARM"]["source"] == "skeleton/automation/swarm"
    assert mappings["AIFT-HIVE"]["source"] == "skeleton/automation/hive"
    assert mappings["AIFT-OVERSEER"]["source"] == "skeleton/automation/overseer"
    assert mappings["AIFT-BUILD-PLANNING"]["source"] == "skeleton/automation/shift_supervisor"


def test_agents_migration_is_recorded_as_canonicalized() -> None:
    plan = json.loads((ROOT / "machine" / "repository_migration_plan.json").read_text(encoding="utf-8"))
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-028")
    assert batch["source"] == "skeleton/agents/"
    assert batch["destination"] == "skeleton/automation/agents/"
    assert batch["state"] == "canonicalized"
