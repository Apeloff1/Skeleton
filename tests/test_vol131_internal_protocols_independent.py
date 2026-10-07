from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from scripts import verify_vol131_internal_protocols as verifier


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vol131-independent-"))
    for relative in (
        verifier.MASTER,
        verifier.AI_TREE,
        verifier.CANONICAL,
        verifier.MIRROR,
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


def test_current_repository_passes_independent_vol131_verification() -> None:
    receipt = verifier.verify_repository(ROOT)

    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["volume"] == "VOL-131"
    assert receipt["verifier"] == "independent-vol131-internal-protocols-v1"
    assert receipt["ai_tree_binding"]["mapping_id"] == "AIFT-NETWORK"
    assert receipt["implementation"]["mirror_parity"] is True
    assert receipt["implementation"]["export_parity"] is True
    assert receipt["implementation"]["required_invariant_count"] >= 20
    assert receipt["implementation"]["required_regression_count"] >= 10
    assert len(receipt["receipt_digest"]) == 64


def test_rejects_protocol_mirror_drift() -> None:
    root = _fixture()
    path = root / verifier.MIRROR
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("protocol mirror drift" in error for error in receipt["errors"])


def test_rejects_network_export_drift() -> None:
    root = _fixture()
    path = root / verifier.MIRROR_INIT
    path.write_text(
        path.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("network export drift" in error for error in receipt["errors"])


def test_rejects_masterplan_requirement_loss() -> None:
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


def test_rejects_premature_completion_promotion() -> None:
    root = _fixture()
    path = root / verifier.MASTER
    data = _load(path)
    volume = next(item for item in data["volumes"] if item["key"] == "VOL-131")
    volume["completion_checkbox"] = True
    _write(path, data)

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("cannot self-sign" in error for error in receipt["errors"])


def test_rejects_ai_tree_mapping_drift() -> None:
    root = _fixture()
    path = root / verifier.AI_TREE
    data = _load(path)
    mapping = next(item for item in data["mappings"] if item["id"] == "AIFT-NETWORK")
    mapping["destination"] = "skeleton/ai/runtime/distributed/network-drift"
    _write(path, data)

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any("exactly one canonical distributed-network" in error for error in receipt["errors"])


def test_rejects_retry_invariant_source_weakening() -> None:
    root = _fixture()
    canonical = root / verifier.CANONICAL
    mirror = root / verifier.MIRROR
    source = canonical.read_text(encoding="utf-8").replace(
        "cannot retry expired envelope",
        "expired retries ignored",
    )
    canonical.write_text(source, encoding="utf-8")
    mirror.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "implementation invariant missing: cannot retry expired envelope" == error
        for error in receipt["errors"]
    )


def test_rejects_required_regression_removal() -> None:
    root = _fixture()
    path = root / verifier.TESTS
    source = path.read_text(encoding="utf-8").replace(
        "test_retry_chain_is_digest_bound_and_bounded",
        "test_retry_chain_removed",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "regression missing: test_retry_chain_is_digest_bound_and_bounded" in error
        for error in receipt["errors"]
    )
