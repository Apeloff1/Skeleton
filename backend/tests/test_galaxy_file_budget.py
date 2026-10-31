"""Explicit Galaxy budgets bound real worker dispatch and durable partial output."""
from __future__ import annotations

import asyncio
from importlib import import_module

import pytest
import zstandard as zstd

from core import build_vault as vault
from routes import galaxy_studio as galaxy
from routes.galaxy_studio_scale import _parse_scale


@pytest.fixture
def bounded_build(tmp_path, monkeypatch):
    monkeypatch.setattr(vault, "BUILDS_ROOT", tmp_path)
    monkeypatch.setattr(vault, "_zctx", lambda: zstd.ZstdCompressor(level=1, threads=0))
    monkeypatch.setattr(galaxy, "_check_build_resources", galaxy._check_build_continuation)
    monkeypatch.setattr(galaxy, "_worker_cooldown", lambda **_kwargs: None)

    async def save(_build):
        return True

    monkeypatch.setattr(galaxy, "_save_build", save)
    from core import databases

    def no_remote_references(*_args, **_kwargs):
        raise RuntimeError("isolated references")

    monkeypatch.setattr(databases, "get_sync_db", no_remote_references)
    builds = []

    def create(limit):
        build = galaxy._create_build("Bounded probe", "rpg", "", "A finite build", target_files=limit)
        builds.append(build)
        return build

    yield create
    for build in builds:
        assert galaxy._physical_build_workers(build["build_id"]) == 0
        galaxy._builds.pop(build["build_id"], None)


def forbidden_padding(*_args, **_kwargs):
    pytest.fail("an explicit file budget must not generate floor padding")


def test_explicit_count_overrides_implicit_scale_and_size_without_changing_defaults():
    parsed = _parse_scale("infinite massive 1tb game", target_files=3, target_size_gb=100)
    assert parsed["target_files"] == parsed["explicit_target_files"] == 3
    assert parsed["multiplier"] == 1
    legacy = _parse_scale("")
    assert legacy["target_files"] == 48_000
    assert "explicit_target_files" not in legacy


def test_real_tiny_generation_stops_and_retains_durable_partial_output(bounded_build, monkeypatch):
    build = bounded_build(3)
    monkeypatch.setattr(galaxy, "_submit_floor_chunk", forbidden_padding)
    monkeypatch.setattr(galaxy, "_generate_floor_padding", forbidden_padding)
    monkeypatch.setattr(galaxy, "_generate_fallback_files", forbidden_padding)
    calls = []
    actual_generate = galaxy._safe_generate_batch

    def generate(build_id, batch):
        calls.append(batch)
        return actual_generate(build_id, batch)

    monkeypatch.setattr(galaxy, "_safe_generate_batch", generate)
    asyncio.run(galaxy._run_background_build(build["build_id"], duration_minutes=1))

    assert calls == [1]
    assert build["status"] == build["_bg_status"] == "failed"
    assert build["_bg_stop_reason"] == "artifact_file_budget_exhausted"
    assert build["_bg_partial_artifacts"] is True
    assert not build.get("completed_at") and not build.get("_bg_completed")
    assert not any(phase["status"] == "completed" for phase in build["phases"])
    assert build["_bg_phase_log"] == []
    assert vault.get_file_count(build["build_id"]) == build["file_count"] == 3
    assert set(vault.get_file_paths(build["build_id"])) == {"DESIGN_DOCUMENT.md", "app.json", "package.json"}
    assert build["files"] == {} and "_file_budget_owner" not in build
    assert not build["_bg_drain_pending"]
    assert build["build_id"] not in galaxy._active_runners
    assert build["build_id"] not in galaxy._background_tasks


def test_manual_tiny_generation_retains_the_same_durable_partial_output(bounded_build, monkeypatch):
    build = bounded_build(3)
    monkeypatch.setattr(galaxy, "_generate_floor_padding", forbidden_padding)
    monkeypatch.setattr(galaxy, "_generate_fallback_files", forbidden_padding)

    with pytest.raises(galaxy.HTTPException) as stopped:
        asyncio.run(galaxy._advance_build(build["build_id"]))

    assert stopped.value.status_code == 503
    assert "artifact_file_budget_exhausted" in stopped.value.detail
    assert build["status"] == build["_bg_status"] == "failed"
    assert build["_bg_stop_reason"] == "artifact_file_budget_exhausted"
    assert build["_bg_partial_artifacts"] is True
    assert build["_vault_preserved"] is True
    assert vault.get_file_count(build["build_id"]) == build["file_count"] == 3
    assert set(vault.get_file_paths(build["build_id"])) == {"DESIGN_DOCUMENT.md", "app.json", "package.json"}
    assert not any(phase["status"] == "completed" for phase in build["phases"])
    assert not build.get("completed_at") and not build.get("_bg_completed")
    assert not build.get("_bg_phase_log")
    assert build["files"] == {} and "_file_budget_owner" not in build
    assert not build["_bg_drain_pending"]
    assert build["build_id"] not in galaxy._active_runners
    assert build["build_id"] not in galaxy._background_tasks


@pytest.mark.parametrize("limit,expected_status,expected_complete", [(100, "completed", 100), (99, "failed", 90)])
def test_real_runner_attests_only_durable_finished_batches_and_never_pads(bounded_build, monkeypatch, limit, expected_status, expected_complete):
    build = bounded_build(limit)
    monkeypatch.setattr(galaxy, "_submit_floor_chunk", forbidden_padding)
    monkeypatch.setattr(galaxy, "_generate_floor_padding", forbidden_padding)
    phases = []

    def finite_phase(phase_id, current):
        phases.append(phase_id)
        files = galaxy._new_phase_files(current)
        files[f"phases/{phase_id}.txt"] = f"Actual fixture content for {phase_id}"
        return files

    monkeypatch.setattr(galaxy, "_call_phase_func", finite_phase)
    asyncio.run(galaxy._run_background_build(build["build_id"], duration_minutes=1))

    assert len(phases) == limit
    assert len(set(phases)) == limit
    assert vault.get_file_count(build["build_id"]) == build["file_count"] == limit
    assert build["status"] == build["_bg_status"] == expected_status
    assert sum(phase["status"] == "completed" for phase in build["phases"]) == expected_complete
    assert len(build["_bg_phase_log"]) == expected_complete // 10
    assert all(entry["status"] == "success" for entry in build["_bg_phase_log"])
    assert bool(build.get("completed_at")) == (expected_status == "completed")
    assert not build["_bg_drain_pending"] and build["files"] == {}
    if expected_status == "failed":
        assert build["_bg_stop_reason"] == "artifact_file_budget_exhausted"
    else:
        assert build["_bg_floor_target"] == 0 and not build.get("_bg_stop_requested")


def test_resume_uses_unique_metadata_paths_and_counts_replacements_once(bounded_build, monkeypatch):
    build = bounded_build(3)
    vault.append_files(build["build_id"], {"same.txt": "old"})
    build.update(_vault_active=True, file_count=1, _vault_file_count=1)
    monkeypatch.setattr(vault, "list_file_paths", forbidden_padding)
    files = galaxy._new_phase_files(build)
    files["same.txt"] = "replacement"
    files["new.txt"] = "new"
    files["last.txt"] = "last"
    assert len(build["_file_budget_owner"]["paths"]) == 3
    assert vault.get_file_count(build["build_id"], pending_paths=build["files"]) == 3
    with pytest.raises(galaxy.GalaxyBuildStopped, match="artifact_file_budget_exhausted"):
        files["too-many.txt"] = "must not be retained"
    assert set(build["files"]) == {"same.txt", "new.txt", "last.txt"}


@pytest.mark.parametrize("module_name,function", [
    ("galaxy_studio_capabilities", "generate_all_capabilities"),
    ("galaxy_studio_gamedev_pipeline", "generate_gamedev_pipeline"),
    ("galaxy_studio_datasets", "generate_datasets"),
])
def test_nested_eager_helpers_share_the_same_finite_pending_owner(bounded_build, module_name, function):
    build = bounded_build(2)
    module = import_module(f"routes.{module_name}")
    with pytest.raises(galaxy.GalaxyBuildStopped, match="artifact_file_budget_exhausted"):
        getattr(module, function)(build, build["title"], build["genre"], files_factory=lambda: galaxy._new_phase_files(build))
    assert len(build["files"]) == len(build["_file_budget_owner"]["paths"]) == 2
    assert build["_bg_stop_requested"] is True
    assert not build.get("completed_at")


def test_global_upper_bound_still_applies_to_explicit_requests(bounded_build, monkeypatch):
    monkeypatch.setattr(galaxy, "GLOBAL_FILE_BUDGET", 2)
    build = bounded_build(1_000_000)
    files = galaxy._new_phase_files(build)
    files["one"] = "one"
    files["two"] = "two"
    with pytest.raises(galaxy.GalaxyBuildStopped, match="artifact_file_budget_exhausted"):
        files["three"] = "three"
    assert set(build["files"]) == {"one", "two"}


def test_default_generation_remains_unbounded_by_an_implicit_floor(bounded_build):
    build = bounded_build(0)
    files = galaxy._new_phase_files(build)
    files["ordinary"] = "ordinary"
    assert type(files) is dict
    assert build["files"] == {}


@pytest.mark.parametrize("emergency", [False, True])
def test_fallback_and_emergency_output_cannot_escape_the_pending_budget(bounded_build, monkeypatch, emergency):
    build = bounded_build(3)
    monkeypatch.setattr(galaxy, "_submit_floor_chunk", forbidden_padding)
    monkeypatch.setattr(galaxy, "_generate_floor_padding", forbidden_padding)

    def unavailable(*_args, **_kwargs):
        raise ValueError("content fixture unavailable")

    # Real dispatch reaches the fallback cascade; neither a degraded phase nor
    # its emergency path can queue an uncounted dictionary beyond the cap.
    for function in set(galaxy._PHASE_FUNC_MAP.values()):
        monkeypatch.setattr(galaxy, function, unavailable)
    monkeypatch.setattr(galaxy, "_phase_generic", unavailable)
    if emergency:
        monkeypatch.setattr(galaxy, "_generate_fallback_files", unavailable)
    asyncio.run(galaxy._run_background_build(build["build_id"], duration_minutes=1))

    assert build["status"] == "failed"
    assert build["_bg_stop_reason"] == "artifact_file_budget_exhausted"
    assert vault.get_file_count(build["build_id"]) == 3
    names = vault.get_file_paths(build["build_id"])
    assert all(name.startswith("stubs/" if emergency else "fallback/") for name in names)
    assert not any(phase["status"] == "completed" for phase in build["phases"])
    assert not build.get("completed_at") and not build["_bg_drain_pending"]
