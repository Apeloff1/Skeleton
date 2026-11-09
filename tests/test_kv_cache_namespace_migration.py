"""Regression coverage for TREE-011 KV-cache facade convergence."""

from __future__ import annotations

import importlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_kv_cache_facade_reexports_canonical_kv_package() -> None:
    legacy = importlib.import_module("skeleton.kv_cache")
    canonical = importlib.import_module("skeleton.kv")

    assert legacy.KVCacheManager is canonical.KVCacheManager
    assert legacy.KVCacheTransaction is canonical.KVCacheTransaction
    assert legacy.KVCacheConfig is canonical.KVCacheConfig
    assert legacy.KVStorageAdapter is canonical.KVStorageAdapter


def test_ai_kv_cache_facade_reexports_canonical_ai_kv_package() -> None:
    legacy = importlib.import_module("skeleton.ai.runtime.inference.kv_cache")
    canonical = importlib.import_module("skeleton.ai.runtime.inference.kv")

    assert legacy.KVCacheManager is canonical.KVCacheManager
    assert legacy.KVCacheTransaction is canonical.KVCacheTransaction
    assert legacy.KVCacheConfig is canonical.KVCacheConfig


def test_ai_tree_native_mapping_has_no_stale_jvm_overlay() -> None:
    manifest = json.loads(
        (ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8")
    )
    mapping = next(item for item in manifest["mappings"] if item["id"] == "AIFT-NATIVE")

    assert "jvm_registry.py" not in mapping.get("overlay_children", [])
