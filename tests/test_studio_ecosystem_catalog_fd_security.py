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


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
                    reason="descriptor-relative no-follow requires POSIX")
def test_catalog_audit_never_reopens_source_documents_by_pathname(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catalog audit shares the loader's race-resistant raw-byte read path."""
    from scripts.check_studio_ecosystem_catalog import audit

    first = catalog.catalog_index()[0]
    root = tmp_path / "catalog"
    root.mkdir()
    original_index = json.loads((catalog.ROOT / "index.json").read_text("utf-8"))
    original_index["projects"] = [first]
    original_index["project_count"] = 1
    (root / "index.json").write_text(json.dumps(original_index), encoding="utf-8")
    shutil.copytree(catalog.ROOT / first["id"], root / first["id"])

    def prohibit_pathname_reads(self: Path) -> bytes:
        raise AssertionError("audit must not reopen source by pathname")

    monkeypatch.setattr(Path, "read_bytes", prohibit_pathname_reads)
    receipt = audit(root=root)
    assert receipt["status"] == "source_valid"
    assert receipt["projects"] == 1
    assert receipt["documents"] == len(catalog.SECTIONS)
    assert receipt["unique_source_digests"] == len(catalog.SECTIONS)
    assert receipt["release_certified"] is False


@pytest.mark.skipif(os.name != "posix" or not hasattr(os, "O_NOFOLLOW"),
                    reason="descriptor-relative no-follow requires POSIX")
def test_catalog_audit_refuses_symlink_source_after_valid_blueprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-validation file swap cannot redirect audit hashing outside root."""
    from scripts import check_studio_ecosystem_catalog as auditor

    first = catalog.catalog_index()[0]
    root = tmp_path / "catalog"
    root.mkdir()
    index = json.loads((catalog.ROOT / "index.json").read_text("utf-8"))
    index["projects"] = [first]
    index["project_count"] = 1
    (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
    project = root / first["id"]
    shutil.copytree(catalog.ROOT / first["id"], project)
    outside = tmp_path / "outside.json"
    outside.write_text('{"secret":"must-not-hash"}', encoding="utf-8")

    original_reader = auditor.read_blueprint
    swapped = False

    def swap_after_validation(project_id: str, *, root: Path):
        nonlocal swapped
        validated = original_reader(project_id, root=root)
        if not swapped:
            swapped = True
            target = root / project_id / "intent.json"
            target.unlink()
            target.symlink_to(outside)
        return validated

    monkeypatch.setattr(auditor, "read_blueprint", swap_after_validation)
    receipt = auditor.audit(root=root)
    assert swapped
    assert receipt["status"] == "source_rejected"
    assert any("unsafe source document" in error for error in receipt["errors"])
    assert receipt["release_certified"] is False
