"""Descriptor-anchored catalog filesystem regressions (POSIX)."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from skeleton.ai.game_builder import studio_ecosystem_catalog as catalog


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
                    reason="descriptor-relative no-follow requires POSIX")
def test_rejects_project_directory_swapped_for_symlink_after_precheck(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = catalog.catalog_index()[0]["id"]
    root = tmp_path / "catalog"
    root.mkdir()
    (root / "index.json").write_bytes((catalog.ROOT / "index.json").read_bytes())
    project = root / source
    shutil.copytree(catalog.ROOT / source, project)
    moved = tmp_path / "relocated"
    original_is_dir = Path.is_dir
    swapped = False

    def swap_after_precheck(path: Path) -> bool:
        nonlocal swapped
        exists = original_is_dir(path)
        if path == project and exists and not swapped:
            swapped = True
            project.rename(moved)
            project.symlink_to(moved, target_is_directory=True)
        return exists

    monkeypatch.setattr(Path, "is_dir", swap_after_precheck)
    with pytest.raises(catalog.StudioEcosystemError):
        catalog.read_blueprint(source, root=root)
    assert swapped


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
                    reason="descriptor-relative no-follow requires POSIX")
def test_rejects_symlinked_catalog_root(tmp_path: Path) -> None:
    root = tmp_path / "actual"
    root.mkdir()
    (root / "index.json").write_text(
        json.dumps({"schema": catalog.SCHEMA, "sections": list(catalog.SECTIONS),
                    "project_count": 1, "projects": [
                        {"id": "safe_project", "genre": "puzzle",
                         "biome": "plain", "theme": "original"}]}),
        encoding="utf-8",
    )
    linked = tmp_path / "linked"
    linked.symlink_to(root, target_is_directory=True)
    with pytest.raises(catalog.StudioEcosystemError):
        catalog.catalog_index(root=linked)
    assert catalog.catalog_index(root=root)[0]["id"] == "safe_project"


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
                    reason="descriptor-relative no-follow requires POSIX")
def test_rejects_in_place_mutation_during_descriptor_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "catalog"
    root.mkdir()
    target = root / "index.json"
    target.write_text('{"value":"before"}', encoding="utf-8")
    original_read = os.read
    changed = False

    def mutate_after_read(fd: int, length: int) -> bytes:
        nonlocal changed
        block = original_read(fd, length)
        if block and not changed:
            changed = True
            with target.open("ab") as stream:
                stream.write(b" ")
                stream.flush()
                os.fsync(stream.fileno())
        return block

    monkeypatch.setattr(os, "read", mutate_after_read)
    with pytest.raises(catalog.StudioEcosystemError, match="changed during read"):
        catalog._read_json(target, root=root)
    assert changed


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "mkfifo"),
                    reason="FIFO contract requires POSIX")
def test_rejects_nonregular_catalog_without_blocking(tmp_path: Path) -> None:
    root = tmp_path / "catalog"
    root.mkdir()
    os.mkfifo(root / "index.json")
    with pytest.raises(catalog.StudioEcosystemError):
        catalog.catalog_index(root=root)
