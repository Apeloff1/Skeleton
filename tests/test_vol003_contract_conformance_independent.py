from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.verify_vol003_contract_conformance import (
    QUALIFICATION_GAP,
    REQUIRED_VOL003_EVALUATIONS,
    REQUIRED_VOL003_PATHS,
    REQUIRED_VOL003_TESTS,
    verify_repository,
)


ROOT = Path(__file__).resolve().parents[1]


def _copy_fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/contract_conformance.json",
        "machine/ai_runtime_schemas.json",
        "machine/capability_interfaces.json",
        "machine/ai_master_plan.json",
        "skeleton/contracts/canonical.py",
        "skeleton/ai/runtime/contracts/canonical.py",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_independent_vol003_accepts_current_pending_closure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _copy_fixture(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "vol003-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "vol003-head"
    assert receipt["volume"] == "VOL-003"
    assert receipt["contract_count"] == 36
    assert receipt["override_count"] == 3
    assert receipt["executed_vector_count"] == 18
    assert len(receipt["vector_ids"]) == 18
    assert set(receipt["source_digests"]) == {
        "catalog",
        "schema_catalog",
        "interface_registry",
    }
    assert receipt["serializer_mirror"]["canonical"] == (
        receipt["serializer_mirror"]["mirror"]
    )
    assert len(receipt["receipt_digest"]) == 64


def test_independent_vol003_rejects_serializer_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    mirror = root / "skeleton/ai/runtime/contracts/canonical.py"
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "canonical contract serializer mirror drift" in receipt["errors"]


def test_independent_vol003_rejects_missing_contract_inventory(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / "machine/contract_conformance.json"
    payload = _load(path)
    payload["entries"].pop()
    _write(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "contract inventory/schema coverage drift" in error
        for error in receipt["errors"]
    )


def test_independent_vol003_rejects_vector_expectation_drift(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / "machine/contract_conformance.json"
    payload = _load(path)
    vector = next(
        row
        for row in payload["vectors"]
        if row["id"] == "JSON-DUPLICATE-KEY"
    )
    vector["expected"] = "accept"
    _write(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "JSON-DUPLICATE-KEY replay mismatch" in error
        for error in receipt["errors"]
    )


def test_independent_vol003_rejects_consumer_derivation_drift(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / "machine/contract_conformance.json"
    payload = _load(path)
    entry = next(
        row
        for row in payload["entries"]
        if row["contract"] == "OperationEnvelope"
    )
    entry["consumer_planes"] = ["ghost-plane"]
    _write(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "OperationEnvelope derived consumer set drift" in error
        for error in receipt["errors"]
    )


def test_independent_vol003_rejects_retired_gap_reappearance(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    catalog = _load(root / "machine/contract_conformance.json")
    retired = catalog["masterplan_binding"]["retired_implementation_gaps"][0]
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-003")
    volume["gaps"] = [retired]
    volume["completion_checkbox"] = False
    volume["completion_checkbox_mark"] = "[ ]"
    _write(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "retired VOL-003 implementation gap reappeared" in error
        for error in receipt["errors"]
    )


def test_independent_vol003_rejects_cleared_gap_without_signoff(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-003")
    volume["gaps"] = []
    volume["completion_checkbox"] = False
    volume["completion_checkbox_mark"] = "[ ]"
    _write(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "VOL-003 cannot clear qualification gap before signoff" in receipt["errors"]


def test_independent_vol003_accepts_signed_closure_state(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-003")
    volume["gaps"] = []
    volume["completion_checkbox"] = True
    volume["completion_checkbox_mark"] = "[x]"
    volume["implementation_status"] = "verified"
    _write(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []


def test_independent_vol003_rejects_signed_pending_gap(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-003")
    volume["gaps"] = [QUALIFICATION_GAP]
    volume["completion_checkbox"] = True
    volume["completion_checkbox_mark"] = "[x]"
    _write(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "VOL-003 cannot remain signed with pending qualification" in receipt["errors"]


def test_independent_vol003_rejects_missing_masterplan_binding(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-003")
    volume["tests"].remove("tests/test_vol003_contract_conformance_independent.py")
    _write(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "VOL-003 test binding incomplete" in error
        for error in receipt["errors"]
    )


def test_independent_vol003_required_bindings_are_nonempty() -> None:
    assert REQUIRED_VOL003_PATHS
    assert REQUIRED_VOL003_TESTS
    assert REQUIRED_VOL003_EVALUATIONS


def test_independent_vol003_rejects_nonportable_numeric_expectation_drift(
    tmp_path: Path,
) -> None:
    root = _copy_fixture(tmp_path)
    path = root / "machine/contract_conformance.json"
    payload = _load(path)
    vector = next(
        row for row in payload["vectors"]
        if row["id"] == "JSON-UNSAFE-POSITIVE-INTEGER"
    )
    vector["expected"] = "accept"
    _write(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "JSON-UNSAFE-POSITIVE-INTEGER replay mismatch" in error
        for error in receipt["errors"]
    )
