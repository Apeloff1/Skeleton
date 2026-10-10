from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from scripts import verify_vol131_internal_protocols as verifier


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vol131-independent-v2-"))
    for relative in (
        verifier.MASTER,
        verifier.AI_TREE,
        verifier.CONTRACT,
        verifier.CONTRACT_MIRROR,
        verifier.EXECUTION,
        verifier.EXECUTION_MIRROR,
        verifier.CANONICAL_INIT,
        verifier.MIRROR_INIT,
        verifier.TESTS,
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


def test_current_repository_has_one_canonical_protocol_authority() -> None:
    receipt = verifier.verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["verifier"] == "independent-vol131-internal-protocols-v2"
    implementation = receipt["implementation"]
    assert implementation["single_envelope_authority"] is True
    assert implementation["contract_mirror_parity"] is True
    assert implementation["mirror_parity"] is True
    assert implementation["export_parity"] is True
    assert set(receipt["ai_tree_binding"]) == {"AIFT-CONTRACTS", "AIFT-NETWORK"}


def test_rejects_shadow_protocol_envelope_in_execution_layer() -> None:
    root = _fixture()
    for relative in (verifier.EXECUTION, verifier.EXECUTION_MIRROR):
        path = root / relative
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\nclass ProtocolEnvelope:\n    pass\n",
            encoding="utf-8",
        )
    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("shadow ProtocolEnvelope" in error for error in receipt["errors"])


def test_rejects_canonical_contract_mirror_drift() -> None:
    root = _fixture()
    path = root / verifier.CONTRACT_MIRROR
    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("canonical contract AI mirror drift" in error for error in receipt["errors"])


def test_rejects_execution_mirror_drift() -> None:
    root = _fixture()
    path = root / verifier.EXECUTION_MIRROR
    path.write_text(path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("execution AI mirror drift" in error for error in receipt["errors"])


def test_rejects_ai_tree_contract_mapping_drift() -> None:
    root = _fixture()
    path = root / verifier.AI_TREE
    data = _load(path)
    mapping = next(item for item in data["mappings"] if item["id"] == "AIFT-CONTRACTS")
    mapping["destination"] = "skeleton/ai/runtime/contracts-drift"
    _write(path, data)
    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("skeleton/contracts AI-tree mapping" in error for error in receipt["errors"])


def test_rejects_retry_guard_weakening() -> None:
    root = _fixture()
    for relative in (verifier.EXECUTION, verifier.EXECUTION_MIRROR):
        path = root / relative
        source = path.read_text(encoding="utf-8").replace(
            "cannot retry expired envelope",
            "expired retry permitted",
        )
        path.write_text(source, encoding="utf-8")
    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "execution invariant missing: cannot retry expired envelope" == error
        for error in receipt["errors"]
    )


def test_rejects_masterplan_protocol_requirement_loss() -> None:
    root = _fixture()
    path = root / verifier.MASTER
    data = _load(path)
    volume = next(item for item in data["volumes"] if item["key"] == "VOL-131")
    volume["requirements"].remove(
        "Use stable envelopes with correlation, causation and deadline metadata."
    )
    _write(path, data)
    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("requirement invariant lost" in error for error in receipt["errors"])
