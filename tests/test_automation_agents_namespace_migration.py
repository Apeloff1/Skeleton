"""Regression coverage for TREE-028 automation-agents migration."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_agent_modules_reexport_canonical_runtime() -> None:
    legacy_routing = importlib.import_module("skeleton.agents.routing")
    canonical_routing = importlib.import_module("skeleton.automation.agents.routing")
    legacy_runtime = importlib.import_module("skeleton.agents.swarm_runtime")
    canonical_runtime = importlib.import_module("skeleton.automation.agents.swarm_runtime")

    assert legacy_routing.RouteCandidate is canonical_routing.RouteCandidate
    assert legacy_routing.AgentDiscovery is canonical_routing.AgentDiscovery
    assert legacy_runtime.SwarmRuntime is canonical_runtime.SwarmRuntime
    assert legacy_runtime.SwarmTask is canonical_runtime.SwarmTask


def test_canonical_and_ai_agent_trees_do_not_import_legacy_namespace() -> None:
    for relative in ("skeleton/automation/agents", "skeleton/ai/agents/core"):
        for path in (ROOT / relative).glob("*.py"):
            assert "skeleton.agents" not in path.read_text(encoding="utf-8"), path


def test_ai_tree_retargets_agents_and_overlays_automation_parent() -> None:
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    agents = next(item for item in manifest["mappings"] if item["id"] == "AIFT-AGENTS")
    automation = next(item for item in manifest["mappings"] if item["id"] == "AIFT-AUTOMATION")

    assert agents["source"] == "skeleton/automation/agents"
    assert agents["destination"] == "skeleton/ai/agents/core"
    tree = subprocess.check_output(["git", "write-tree"], cwd=ROOT, text=True).strip()
    assert agents["source_git_object_sha"] == subprocess.check_output(
        ["git", "rev-parse", f'{tree}:{agents["source"]}'], cwd=ROOT, text=True
    ).strip()
    assert "agents" in automation["overlay_children"]


def test_agents_migration_is_recorded_as_canonicalized() -> None:
    plan = json.loads((ROOT / "machine/repository_migration_plan.json").read_text(encoding="utf-8"))
    batch = next(item for item in plan["batches"] if item["id"] == "TREE-028")

    assert batch["source"] == "skeleton/agents/"
    assert batch["destination"] == "skeleton/automation/agents/"
    assert batch["state"] == "canonicalized"
