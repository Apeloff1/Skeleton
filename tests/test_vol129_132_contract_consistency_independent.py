from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from scripts import verify_vol129_132_contract_consistency as verifier


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vol129-132-independent-"))
    for relative in (
        verifier.MASTER,
        verifier.RUNTIME_SCHEMAS,
        verifier.CONFORMANCE,
        verifier.SCHEMA_REGISTRY,
        verifier.COMPATIBILITY,
        verifier.STATE_TOPOLOGY,
        verifier.CONSISTENCY_PROFILES,
        verifier.SCHEMA_GUARD,
        verifier.SCHEMA_GUARD_MIRROR,
        verifier.CONSISTENCY_RUNTIME,
        verifier.CONSISTENCY_MIRROR,
        verifier.PROTOCOL_CONTRACT,
        verifier.PROTOCOL_CONTRACT_MIRROR,
        verifier.PROTOCOL_EXECUTION,
        verifier.PROTOCOL_EXECUTION_MIRROR,
    ):
        source = ROOT / relative
        target = temp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return temp


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def test_current_repository_passes_independent_contract_consistency_verification() -> None:
    receipt = verifier.verify_repository(ROOT)

    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["verifier"] == "independent-vol129-132-contract-consistency-v1"
    assert receipt["volumes"] == ["VOL-129", "VOL-130", "VOL-131", "VOL-132"]
    assert receipt["schemas"]["runtime_schema_count"] == 40
    assert receipt["schemas"]["registered_schema_count"] == 40
    assert receipt["compatibility"]["schema_matrix_count"] == 40
    assert receipt["compatibility"]["guard_mirror_parity"] is True
    assert receipt["consistency"]["profile_count"] == 21
    assert receipt["consistency"]["runtime_mirror_parity"] is True
    assert receipt["protocol"]["single_envelope_authority"] is True
    assert len(receipt["receipt_digest"]) == 64


def test_rejects_schema_registry_identity_drift() -> None:
    root = _fixture()
    path = root / verifier.SCHEMA_REGISTRY
    data = _load(path)
    target = next(
        row for row in data["schemas"]
        if row["record_name"] == "ProtocolEnvelope"
    )
    target["schema_id"] = "SCHEMA-ProtocolEnvelope-drift"
    _write(path, data)

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("stable schema identity drift" in error for error in receipt["errors"])


def test_rejects_runtime_schema_inventory_loss() -> None:
    root = _fixture()
    path = root / verifier.RUNTIME_SCHEMAS
    data = _load(path)
    data["records"].pop("ProtocolReceipt")
    _write(path, data)

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("expected 40 registered runtime schemas" in error for error in receipt["errors"])
    assert any("runtime schema missing ProtocolReceipt" in error for error in receipt["errors"])


def test_rejects_compatibility_matrix_drift() -> None:
    root = _fixture()
    path = root / verifier.COMPATIBILITY
    data = _load(path)
    data["schema_matrix"][0]["supported_versions"] = [999]
    _write(path, data)

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("exact registry projection" in error for error in receipt["errors"])


def test_rejects_schema_evolution_mirror_drift() -> None:
    root = _fixture()
    path = root / verifier.SCHEMA_GUARD_MIRROR
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# mirror drift\n",
        encoding="utf-8",
    )

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("schema evolution AI mirror drift" in error for error in receipt["errors"])


def test_rejects_consistency_unknown_policy_weakening() -> None:
    root = _fixture()
    path = root / verifier.CONSISTENCY_PROFILES
    data = _load(path)
    data["profiles"][0]["unknown_policy"] = "serve"
    _write(path, data)

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("permits unknown state" in error for error in receipt["errors"])


def test_rejects_projection_without_source_first_write() -> None:
    root = _fixture()
    path = root / verifier.CONSISTENCY_PROFILES
    data = _load(path)
    row = next(
        item for item in data["profiles"]
        if item["authority"] in {"derived", "durable-projection"}
    )
    row["write_guarantee"] = "durable_commit_ack"
    _write(path, data)

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("projection is not source-first" in error for error in receipt["errors"])


def test_rejects_consistency_runtime_mirror_drift() -> None:
    root = _fixture()
    path = root / verifier.CONSISTENCY_MIRROR
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# mirror drift\n",
        encoding="utf-8",
    )

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("consistency runtime AI mirror drift" in error for error in receipt["errors"])


def test_rejects_shadow_protocol_envelope_authority() -> None:
    root = _fixture()
    for relative in (
        verifier.PROTOCOL_EXECUTION,
        verifier.PROTOCOL_EXECUTION_MIRROR,
    ):
        path = root / relative
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\nclass ProtocolEnvelope:\n    pass\n",
            encoding="utf-8",
        )

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("shadow ProtocolEnvelope" in error for error in receipt["errors"])


def test_rejects_protocol_execution_mirror_drift() -> None:
    root = _fixture()
    path = root / verifier.PROTOCOL_EXECUTION_MIRROR
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# mirror drift\n",
        encoding="utf-8",
    )

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("protocol execution mirror drift" in error for error in receipt["errors"])


def test_rejects_masterplan_gap_binding_loss() -> None:
    root = _fixture()
    path = root / verifier.MASTER
    data = _load(path)
    volume = next(row for row in data["volumes"] if row["key"] == "VOL-132")
    volume["gaps"].remove("bind guarantees to stores")
    _write(path, data)

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("VOL-132 implementation gap binding drift" == error for error in receipt["errors"])
