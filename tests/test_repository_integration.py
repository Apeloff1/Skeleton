"""Acceptance checks for the combined namespace migrations and portable tree."""
from __future__ import annotations

from collections import Counter
import importlib
import json
from pathlib import Path
import subprocess
from typing import get_type_hints

ROOT = Path(__file__).resolve().parents[1]


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_integrated_source_identities_match_the_index() -> None:
    """CI checks a committed tree; local callers stage their integration first."""
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    ids = {
        "AIFT-APPLICATION", "AIFT-DISTRIBUTED", "AIFT-RESEARCH", "AIFT-KNOWLEDGE",
        "AIFT-PROVENANCE", "AIFT-TOOLS", "AIFT-SIMULATION", "AIFT-GAME",
        "AIFT-SCHOOL", "AIFT-LEARNING", "AIFT-KERNEL", "AIFT-SWARM", "AIFT-NETWORK", "AIFT-ORGANISM", "AIFT-AUTOMATION", "AIFT-GALAXY",
    }
    mappings = {item["id"]: item for item in manifest["mappings"]}
    tree = _git("write-tree")
    for name in sorted(ids):
        item = mappings[name]
        assert item["source_git_object_sha"] == _git("rev-parse", f'{tree}:{item["source"]}'), name
    assert manifest["pre_move_readiness"]["batch_counts"] == dict(
        Counter(item["move_batch"] for item in manifest["mappings"])
    )


def test_migrated_capabilities_load_the_canonical_module() -> None:
    from skeleton.app.runtime.capability_manifest import get_capability
    from skeleton.app.runtime.capability_runtime import CapabilityLoader

    loader = CapabilityLoader()
    for name, module in (
        ("social", "skeleton.research.social"),
        ("galaxy", "skeleton.distributed.galaxy"),
        ("agents", "skeleton.automation.agents"),
        ("swarm", "skeleton.automation.swarm"),
    ):
        assert get_capability(name).module == module
        assert loader.resolve(name) is importlib.import_module(module)


def test_agent_identity_supports_named_ballots_and_generated_rosters() -> None:
    from skeleton.kernel.ids import AgentId
    from skeleton.automation.swarm.auction import AuctionBid

    first, second = AgentId.new(), AgentId.new()
    assert isinstance(first, AgentId)
    assert first.startswith("agent-")
    assert first != second
    named = AgentId("alice")
    assert {named: "yes"}["alice"] == "yes"
    assert json.loads(json.dumps({"agent": named})) == {"agent": "alice"}
    assert get_type_hints(AuctionBid)["agent_id"] is AgentId


def test_frontend_path_components_have_one_case_spelling() -> None:
    spellings: dict[str, str] = {}
    for name in _git("ls-files", "frontend").splitlines():
        parts = name.split("/")
        for end in range(1, len(parts) + 1):
            prefix = "/".join(parts[:end])
            previous = spellings.setdefault(prefix.casefold(), prefix)
            assert previous == prefix, (previous, prefix)
