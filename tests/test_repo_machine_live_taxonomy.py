from __future__ import annotations

from pathlib import Path

from skeleton.repo_machine.atlas import placement_for_path
from skeleton.repo_machine.builder import build_repository_model
from skeleton.repo_machine.config import load_machine_config

ROOT = Path(__file__).resolve().parents[1]


def test_local_build_outputs_do_not_pollute_the_repository_model(tmp_path: Path) -> None:
    config_dir = tmp_path / ".machine"
    config_dir.mkdir()
    (config_dir / "repository.toml").write_bytes((ROOT / ".machine/repository.toml").read_bytes())
    paths = (
        "frontend/node_modules/example/index.js",
        "frontend/dist/index.js",
        "frontend/.expo/types/router.d.ts",
        "skeleton.egg-info/PKG-INFO",
        "frontend/components/Editor.tsx",
        "skeleton/build/compiler.py",
    )
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# fixture\n", encoding="utf-8")
    model = build_repository_model(tmp_path)
    indexed = {item.path for item in model.files}
    assert set(paths[:4]).isdisjoint(indexed)
    assert set(paths[4:]) <= indexed


def test_all_skeleton_top_level_directories_have_machine_placement() -> None:
    config = load_machine_config(ROOT)
    skeleton_root = ROOT / "skeleton"

    unclassified: list[str] = []
    for child in sorted(path for path in skeleton_root.iterdir() if path.is_dir()):
        if child.name + "/" in config.ignore_prefixes:
            continue
        placement = placement_for_path(config, f"skeleton/{child.name}/__init__.py")
        if placement.zone == "unclassified":
            unclassified.append(child.name)

    assert unclassified == []


def test_performance_and_qualification_roots_are_quality_owned() -> None:
    """New standalone evidence packages never inherit AI runtime ownership."""
    config = load_machine_config(ROOT)
    for relative in (
        "skeleton/perfgate/__init__.py",
        "skeleton/qualification/__init__.py",
    ):
        assert (ROOT / relative).is_file()
        placement = placement_for_path(config, relative)
        assert (placement.zone, placement.owner, placement.lifecycle) == (
            "quality", "quality-plane", "canonical"
        )


def test_profiler_runtime_is_owned_by_platform_observability() -> None:
    config = load_machine_config(ROOT)
    placement = placement_for_path(config, "skeleton/perf_profiler/runtime.py")
    assert (placement.zone, placement.owner, placement.lifecycle) == (
        "platform", "platform-runtime", "canonical"
    )


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


def test_runtime_journals_do_not_hide_canonical_provenance_sources() -> None:
    from skeleton.repo_machine.builder import RepositoryModelBuilder

    builder = RepositoryModelBuilder(ROOT)
    assert builder._ignored("chronicle/board.json")
    assert builder._ignored(".skeleton/organism/chronicle/index.json")
    assert not builder._ignored("skeleton/provenance/chronicle/store.py")
    assert placement_for_path(builder.config, "skeleton/provenance/chronicle/store.py").zone == "provenance"


def test_governed_storage_and_release_cockpit_retain_existing_owners() -> None:
    config = load_machine_config(ROOT)
    storage = placement_for_path(config, "skeleton/storage/cas/__init__.py")
    cockpit = placement_for_path(config, "skeleton/ops/cockpit/smoke_verdict.py")
    assert (storage.zone, storage.owner) == ("platform", "platform-runtime")
    assert (cockpit.zone, cockpit.owner) == ("build-delivery", "delivery-plane")


def test_godot_export_and_legacy_mass_build_have_explicit_existing_owners() -> None:
    """Every nested legacy path resolves to its explicitly governed delivery root."""
    config = load_machine_config(ROOT)
    for candidate, canonical in (
        ("skeleton/godot_export/runner.py", "skeleton/godot_export/export.py"),
        ("skeleton/mass_build/B081/contract.py", "skeleton/mass_build/manifest.py"),
    ):
        observed = placement_for_path(config, candidate)
        expected = placement_for_path(config, canonical)
        assert (observed.zone, observed.owner, observed.lifecycle) == (
            expected.zone, expected.owner, expected.lifecycle
        )
        assert (observed.zone, observed.owner, observed.lifecycle) == (
            "build-delivery", "delivery-plane", "canonical"
        )


def test_godot_export_and_mass_build_are_owned_by_delivery_plane() -> None:
    config = load_machine_config(ROOT)
    for path in (
        "skeleton/godot_export/export.py",
        "skeleton/mass_build/manifest.py",
    ):
        placement = placement_for_path(config, path)
        assert (placement.zone, placement.owner, placement.lifecycle) == (
            "build-delivery",
            "delivery-plane",
            "canonical",
        )

def test_game_provider_environment_remains_explicitly_source_retained() -> None:
    """A game-world replay adapter must not inherit credential-provider AI authority."""
    import json

    source = "skeleton/provider_environment.py"
    candidate = ROOT / source
    assert candidate.is_file() and not candidate.is_symlink()
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    retained = [
        record for record in manifest["retained_outside_ai_tree"]
        if record.get("path") == source
    ]
    assert len(retained) == 1
    assert "game-environment" in retained[0]["owner"]
    assert "outside credential-provider AI tree" in retained[0]["reason"]
    assert all(record.get("source") != source for record in manifest["mappings"])
