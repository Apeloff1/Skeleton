"""Catalog resource admission includes every pinned runtime library path."""
from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

import pytest

from skeleton.ai.runtime.inference.catalog import LocalModelCatalog, LocalModelCatalogError

pytestmark = pytest.mark.skipif(not hasattr(os, "O_NOFOLLOW"), reason="pinned libraries require no-follow opens")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deployment(directory: Path) -> tuple[Path, tuple[Path, ...]]:
    directory.mkdir()
    runtime_dir = directory / "runtime"
    runtime_dir.mkdir()
    executable = runtime_dir / "llama-cli"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    library = runtime_dir / "libggml.so"
    library.write_bytes(b"library" * 512)
    model = directory / "model.gguf"
    model.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 2, 1) + struct.pack("<Q", 20)
                      + b"general.architecture" + struct.pack("<I", 8)
                      + struct.pack("<Q", 5) + b"llama" + b"model")
    manifest = directory / "deployment.json"
    manifest.write_text(json.dumps({
        "schema_version": "skeleton.local_model.deployment.v1", "runtime_kind": "llama.cpp-cli",
        "model_id": "model", "executable_path": "runtime/llama-cli",
        "executable_sha256": _digest(executable), "model_path": "model.gguf",
        "model_sha256": _digest(model), "runtime_libraries": {library.name: _digest(library)},
    }), encoding="utf-8")
    return manifest, (manifest, executable, model, library)


def _catalog(path: Path, manifests: list[Path], budget: int) -> None:
    rows = [
        {"model_id": f"route-{index}", "kind": "deployment", "path": str(manifest), "sha256": _digest(manifest)}
        for index, manifest in enumerate(manifests)
    ]
    path.write_text(json.dumps({"schema_version": "skeleton.local_model.catalog.v1",
                                "primary_model_id": "route-0", "max_total_artifact_bytes": budget,
                                "models": rows}), encoding="utf-8")


def test_catalog_rejects_aggregate_library_bytes_even_when_each_deployment_fits(tmp_path: Path) -> None:
    first, files_one = _deployment(tmp_path / "one")
    second, files_two = _deployment(tmp_path / "two")
    exact_bytes = sum(path.stat().st_size for path in (*files_one, *files_two))
    limit = exact_bytes - 1
    assert all(sum(path.stat().st_size for path in files) <= limit for files in (files_one, files_two))
    catalog = tmp_path / "catalog.json"
    _catalog(catalog, [first, second], limit)
    with pytest.raises(LocalModelCatalogError, match="referenced-artifact byte budget"):
        LocalModelCatalog.load(catalog)
    _catalog(catalog, [first, second], exact_bytes)
    loaded = LocalModelCatalog.load(catalog)
    assert loaded.referenced_artifact_bytes == exact_bytes


def test_shared_library_path_counted_once_but_distinct_alias_path_counted(tmp_path: Path) -> None:
    first, files = _deployment(tmp_path / "shared")
    second = first.with_name("other-deployment.json")
    second.write_bytes(first.read_bytes())
    catalog = tmp_path / "catalog.json"
    unique_bytes = sum(path.stat().st_size for path in (*files, second))
    _catalog(catalog, [first, second], unique_bytes)
    loaded = LocalModelCatalog.load(catalog)
    assert loaded.referenced_artifact_bytes == unique_bytes

    # A separate path is budgeted even when a hard link shares its inode.
    library = files[-1]
    alias = library.with_name("libggml.so.0")
    os.link(library, alias)
    payload = json.loads(first.read_text(encoding="utf-8"))
    payload["runtime_libraries"][alias.name] = _digest(alias)
    first.write_text(json.dumps(payload), encoding="utf-8")
    second.write_bytes(first.read_bytes())
    all_bytes = sum(path.stat().st_size for path in (*files, second, alias))
    _catalog(catalog, [first, second], all_bytes - 1)
    with pytest.raises(LocalModelCatalogError):
        LocalModelCatalog.load(catalog)
    _catalog(catalog, [first, second], all_bytes)
    assert LocalModelCatalog.load(catalog).referenced_artifact_bytes == all_bytes
