"""Canonical offline model inventory with real immutable shard store."""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
import pytest

from skeleton.ai.model_runtime.flgb_model_runtime import ModelIdentity, WeightLoadPlan, WeightShard
from skeleton.ai.model_runtime.offline_inventory import (
    OfflineInventoryError, inventory_offline_weights, main,
)
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore


def _stage(root: Path, *, payload: bytes = b"real offline weights") -> tuple[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    src = root / "weights.bin"
    src.write_bytes(payload)
    digest = sha256(payload).hexdigest()
    identity = ModelIdentity("offline-test", "revision-1", "tiny", digest, digest, digest)
    shard = WeightShard(0, digest, len(payload), "local")
    plan = WeightLoadPlan(identity.identity_digest, (shard,), len(payload))
    plan_digest = WeightShardStore(root / "store").stage_plan(identity, plan, {0: src})
    return plan_digest, root / "store"


def test_verified_inventory_is_deterministic_and_offline(tmp_path: Path) -> None:
    digest, store = _stage(tmp_path)
    first = inventory_offline_weights(store)
    second = inventory_offline_weights(store)
    assert first == second
    assert first["model_count"] == 1
    assert first["models"][0]["plan_digest"] == digest
    assert first["device_qualification"] == "not_assessed"
    assert first["model_activation"] == "not_performed"
    assert "weights.bin" not in json.dumps(first)


def test_corrupt_object_refuses_partial_success(tmp_path: Path) -> None:
    digest, store = _stage(tmp_path)
    object_path = next((store / "objects").glob("*/*"))
    object_path.write_bytes(b"tampered")
    with pytest.raises(OfflineInventoryError, match="verification failed"):
        inventory_offline_weights(store)


def test_corrupt_manifest_refuses_inventory(tmp_path: Path) -> None:
    digest, store = _stage(tmp_path)
    (store / "manifests" / (digest + ".json")).write_text("{}")
    with pytest.raises(OfflineInventoryError, match="verification failed"):
        inventory_offline_weights(store)


def test_unknown_manifest_file_is_not_silently_ignored(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    (store / "manifests" / "unfinished.tmp").write_text("incomplete")
    with pytest.raises(OfflineInventoryError, match="unexpected"):
        inventory_offline_weights(store)


def test_symlinked_manifest_rejected(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    (store / "manifests" / ("0" * 64 + ".json")).symlink_to("missing")
    with pytest.raises(OfflineInventoryError, match="unexpected"):
        inventory_offline_weights(store)


def test_symlinked_store_directory_rejected(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(store, target_is_directory=True)
    with pytest.raises(OfflineInventoryError, match="real directory"):
        inventory_offline_weights(alias)


def test_inventory_fails_closed_when_entry_budget_exhausted(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    with pytest.raises(OfflineInventoryError, match="entry budget"):
        inventory_offline_weights(store, max_entries=0)


def test_inventory_fails_closed_when_byte_budget_exhausted(tmp_path: Path) -> None:
    _, store = _stage(tmp_path)
    with pytest.raises(OfflineInventoryError):
        inventory_offline_weights(store, max_weight_bytes=2)


def test_inventory_cli_returns_canonical_receipt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, store = _stage(tmp_path)
    assert main([str(store)]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["model_count"] == 1
    assert len(result["digest"]) == 64


def test_missing_store_is_never_created_by_inventory(tmp_path: Path) -> None:
    path = tmp_path / "absent"
    with pytest.raises(OfflineInventoryError):
        inventory_offline_weights(path)
    assert not path.exists()
