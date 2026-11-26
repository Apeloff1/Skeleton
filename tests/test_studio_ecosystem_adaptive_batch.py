"""An indexed local corpus may grow beyond a legacy fixed project count."""
from collections import namedtuple
from pathlib import Path

import pytest

import skeleton.ai.game_builder.studio_ecosystem_batch as batch
from skeleton.ai.game_builder.studio_ecosystem_catalog import StudioEcosystemError


def test_more_than_256_registered_projects_reach_compiler(tmp_path: Path, monkeypatch):
    project_ids = tuple(f"studio_large_{i:04d}" for i in range(257))
    monkeypatch.setattr(batch, "list_blueprints", lambda **kwargs: [
        {"id": pid} for pid in project_ids
    ])
    monkeypatch.setattr(batch, "read_blueprint", lambda _: {"project": "mock"})

    class CompilerReached(Exception):
        pass

    def stop_at_compiler(*args, **kwargs):
        raise CompilerReached()

    monkeypatch.setattr(batch, "compile_preview", stop_at_compiler)
    with pytest.raises(CompilerReached):
        batch.materialize_previews(
            tmp_path, authorized=True, project_ids=project_ids,
        )
    assert not (tmp_path / project_ids[0]).exists()


def test_unmeasured_or_exhausted_disk_fails_before_writes(tmp_path: Path, monkeypatch):
    Usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(batch.shutil, "disk_usage", lambda _: Usage(8_000_000, 7_000_000, 1_000_000))
    with pytest.raises(StudioEcosystemError, match="insufficient disk"):
        batch.materialize_previews(
            tmp_path, authorized=True,
            project_ids=("studio_puzzle_expedition_copper_mesa",),
        )
    assert not any(tmp_path.iterdir())


def test_bool_or_nonpositive_explicit_budget_is_not_accepted(tmp_path: Path):
    for amount in (True, 0, -1):
        with pytest.raises(StudioEcosystemError):
            batch.materialize_previews(
                tmp_path, authorized=True,
                project_ids=("studio_puzzle_expedition_copper_mesa",),
                max_artifact_bytes=amount,
            )
