from __future__ import annotations

from pathlib import Path

from skeleton.repo_machine.atlas import placement_for_path
from skeleton.repo_machine.config import load_machine_config


ROOT = Path(__file__).resolve().parents[1]


def test_all_skeleton_top_level_directories_have_machine_placement() -> None:
    config = load_machine_config(ROOT)
    skeleton_root = ROOT / "skeleton"

    unclassified: list[str] = []
    for child in sorted(path for path in skeleton_root.iterdir() if path.is_dir()):
        placement = placement_for_path(config, f"skeleton/{child.name}/__init__.py")
        if placement.zone == "unclassified":
            unclassified.append(child.name)

    assert unclassified == []


def test_repaired_runtime_roots_have_expected_owners() -> None:
    config = load_machine_config(ROOT)

    frontier = placement_for_path(config, "skeleton/frontier/agent_runtime.py")
    pipelines = placement_for_path(config, "skeleton/pipelines/gameforge.py")
    platform = placement_for_path(config, "skeleton/platform/godot_adapter.py")

    assert (frontier.zone, frontier.owner, frontier.lifecycle) == (
        "frontier-runtime",
        "frontier-runtime",
        "canonical",
    )
    assert (pipelines.zone, pipelines.owner, pipelines.lifecycle) == (
        "build-delivery",
        "delivery-plane",
        "canonical",
    )
    assert (platform.zone, platform.owner, platform.lifecycle) == (
        "simulation",
        "simulation-runtime",
        "canonical",
    )
