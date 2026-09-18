"""Fail-closed regressions for the durable-state inventory (#969 S171)."""
from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.reliability.state_inventory import (
    CONFLICT_DOMAIN,
    FAMILIES,
    FAMILY_SET,
    INVENTORY_VERSION,
    STORES,
    TASK_KEY,
    DurableStore,
    UnknownDurableStoreError,
    assert_inventory_closed,
    collect_violations,
    inventory_table,
    require_store,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _classified(**overrides: object) -> DurableStore:
    values: dict[str, object] = {
        "store_id": "organism.quality_state",
        "family": "quality_state",
        "status": "classified",
        "format": "jsonl quality/repair rows",
        "owner": "skeleton.organism.quality_state",
        "owner_path": "skeleton/organism/quality_state.py",
        "persistence": ".skeleton/organism/quality.jsonl",
        "restart_durable": True,
        "corruption": "skip JSONDecodeError lines",
        "recovery": "skip corrupt lines",
        "corruption_policy": "skip_corrupt",
        "recovery_policy": "skip",
        "discovery_name": "quality_state",
        "evidence": ("skeleton/organism/quality_state.py",),
        "notes": "",
    }
    values.update(overrides)
    return DurableStore(**values)  # type: ignore[arg-type]


def test_task_identity_and_inventory_version_are_stable() -> None:
    assert TASK_KEY == "reserve-S171-durable-state-inventory"
    assert CONFLICT_DOMAIN == "reliability.readonly.state_inventory"
    assert INVENTORY_VERSION == 1
    assert FAMILIES == (
        "vault",
        "swarm_durable",
        "quality_state",
        "provenance_ledger",
        "sqlite_collection",
    )


def test_repository_durable_state_inventory_is_closed() -> None:
    assert collect_violations(REPO_ROOT, require_paths=True, require_families=True) == []
    assert_inventory_closed(REPO_ROOT)


def test_inventory_covers_required_families_with_owners_and_recovery() -> None:
    rows = inventory_table()
    assert rows
    families = {row["family"] for row in rows}
    assert FAMILY_SET <= families
    statuses = {row["status"] for row in rows}
    assert statuses <= {"classified", "unknown"}
    assert "unknown" not in statuses
    for row in rows:
        assert row["id"]
        assert row["format"]
        assert row["owner"]
        assert row["owner_path"]
        assert row["persistence"]
        assert row["corruption"]
        assert row["recovery"]
        assert row["evidence"]
        assert (REPO_ROOT / str(row["owner_path"])).is_file()


def test_quality_state_is_classified_as_skip_corrupt_not_rewritten() -> None:
    store = require_store("organism.quality_state")
    assert store.family == "quality_state"
    assert store.corruption_policy == "skip_corrupt"
    assert store.recovery_policy == "skip"
    assert store.owner_path == "skeleton/organism/quality_state.py"
    source = (REPO_ROOT / store.owner_path).read_text(encoding="utf-8")
    assert "except json.JSONDecodeError" in source
    assert "continue" in source


def test_vault_worm_audit_and_sqlite_collection_fail_closed_on_corruption() -> None:
    audit = require_store("vault.worm_audit")
    collection = require_store("frontier.sqlite_collection")
    swarm = require_store("swarm.durable")
    cognition = require_store("cognition.provenance")

    assert audit.corruption_policy == "fail_closed"
    assert audit.recovery_policy == "refuse"
    assert audit.restart_durable is True
    assert "AuditChainBroken" in audit.corruption

    assert collection.family == "sqlite_collection"
    assert collection.corruption_policy == "fail_closed"
    assert collection.recovery_policy == "refuse"
    assert "MemoryStoreCorruptionError" in collection.corruption

    assert swarm.family == "swarm_durable"
    assert swarm.corruption_policy == "fail_closed"
    assert "DurableSwarmError" in swarm.corruption
    assert "SwarmRecoveryManager" in swarm.format

    assert cognition.family == "provenance_ledger"
    assert cognition.corruption_policy == "fail_closed"


def test_unknown_store_id_fails_closed() -> None:
    with pytest.raises(UnknownDurableStoreError, match="unknown durable store: physics.world"):
        require_store("physics.world")
    with pytest.raises(UnknownDurableStoreError, match="normalized string"):
        require_store("  vault.worm_audit  ")
    with pytest.raises(UnknownDurableStoreError, match="normalized string"):
        require_store("")


def test_unclassified_catalog_row_fails_closed() -> None:
    store = _classified(status="unknown")
    with pytest.raises(UnknownDurableStoreError, match="unclassified durable store"):
        require_store("organism.quality_state", inventory=(store,))


def test_unknown_status_in_catalog_fails_closed(tmp_path: Path) -> None:
    store = _classified(status="mystery")
    _write(tmp_path, store.owner_path, "VALUE = 1\n")
    violations = collect_violations(
        tmp_path,
        inventory=(store,),
        require_paths=True,
        require_families=False,
    )
    assert any("unknown status fails closed" in item for item in violations)


def test_incomplete_classification_fails_closed(tmp_path: Path) -> None:
    store = _classified(format="", recovery="")
    _write(tmp_path, store.owner_path, "VALUE = 1\n")
    violations = collect_violations(
        tmp_path,
        inventory=(store,),
        require_paths=False,
        require_families=False,
    )
    assert any("missing format" in item for item in violations)
    assert any("missing recovery" in item for item in violations)


def test_unknown_family_fails_closed(tmp_path: Path) -> None:
    store = _classified(family="physics")
    violations = collect_violations(
        tmp_path,
        inventory=(store,),
        require_paths=False,
        require_families=False,
    )
    assert any("unknown family fails closed: physics" in item for item in violations)


def test_unlisted_provenance_ledger_is_unknown(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "skeleton/newplane/ledger.py",
        "class ProvenanceLedger:\n    pass\n",
    )
    violations = collect_violations(
        tmp_path,
        inventory=(),
        require_paths=False,
        require_families=False,
    )
    assert any("skeleton/newplane/ledger.py::ProvenanceLedger" in item for item in violations)
    assert any("unknown durable store fails closed" in item for item in violations)


def test_unlisted_sqlite_collection_is_unknown(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "skeleton/frontier/extra_memory.py",
        "class SQLiteCollection:\n    pass\n",
    )
    violations = collect_violations(
        tmp_path,
        inventory=(),
        require_paths=False,
        require_families=False,
    )
    assert any(
        "skeleton/frontier/extra_memory.py::SQLiteCollection" in item for item in violations
    )


def test_unlisted_swarm_durable_bridge_is_unknown(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "skeleton/agents/other_durable.py",
        "class SwarmDurableBridge:\n    pass\n",
    )
    violations = collect_violations(
        tmp_path,
        inventory=(),
        require_paths=False,
        require_families=False,
    )
    assert any(
        "skeleton/agents/other_durable.py::SwarmDurableBridge" in item for item in violations
    )


def test_inventory_does_not_own_replication_or_physics() -> None:
    source = (REPO_ROOT / "skeleton/reliability/state_inventory.py").read_text(encoding="utf-8")
    assert "snapshot_replication" not in source
    assert "SnapshotReplicator" not in source
    assert "skeleton.physics" not in source
    for store in STORES:
        assert store.family != "physics"
        assert "rewrite" not in store.owner_path


def test_missing_classified_family_fails_closed(tmp_path: Path) -> None:
    store = _classified()
    _write(tmp_path, store.owner_path, "VALUE = 1\n")
    violations = collect_violations(
        tmp_path,
        inventory=(store,),
        require_paths=False,
        require_families=True,
    )
    assert any("missing classified family fails closed" in item for item in violations)
    assert any("vault" in item for item in violations)


def test_duplicate_store_id_fails_closed(tmp_path: Path) -> None:
    first = _classified()
    second = _classified(owner_path="skeleton/organism/other.py")
    violations = collect_violations(
        tmp_path,
        inventory=(first, second),
        require_paths=False,
        require_families=False,
    )
    assert any("duplicate store_id fails closed" in item for item in violations)
