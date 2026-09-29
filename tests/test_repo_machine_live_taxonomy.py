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
    legacy_pipelines = placement_for_path(config, "skeleton/pipelines/gameforge.py")
    canonical_pipelines = placement_for_path(
        config, "skeleton/forge/pipelines/gameforge.py"
    )
    legacy_platform = placement_for_path(
        config, "skeleton/platform/godot_adapter.py"
    )
    canonical_platform = placement_for_path(
        config, "skeleton/simulation/platform/godot_adapter.py"
    )

    assert (frontier.zone, frontier.owner, frontier.lifecycle) == (
        "frontier-runtime",
        "frontier-runtime",
        "canonical",
    )
    assert (
        legacy_pipelines.zone,
        legacy_pipelines.owner,
        legacy_pipelines.lifecycle,
    ) == ("pipelines-compat", "delivery-plane", "transitional")
    assert (
        canonical_pipelines.zone,
        canonical_pipelines.owner,
        canonical_pipelines.lifecycle,
    ) == ("build-delivery", "delivery-plane", "canonical")
    assert (
        legacy_platform.zone,
        legacy_platform.owner,
        legacy_platform.lifecycle,
    ) == ("platform-compat", "simulation-runtime", "transitional")
    assert (
        canonical_platform.zone,
        canonical_platform.owner,
        canonical_platform.lifecycle,
    ) == ("simulation", "simulation-runtime", "canonical")
