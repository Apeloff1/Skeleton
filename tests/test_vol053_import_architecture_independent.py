from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from scripts import verify_vol053_import_architecture as verifier


ROOT = Path(__file__).resolve().parents[1]


def _fixture() -> Path:
    temp = Path(tempfile.mkdtemp(prefix="vol053-independent-"))
    for relative in (
        verifier.MASTER,
        verifier.LAYERS,
        verifier.REGISTRY,
        verifier.LAYER_VALIDATOR,
        verifier.WHEEL_VALIDATOR,
        verifier.LAYER_TESTS,
        verifier.WHEEL_TESTS,
    ):
        source = ROOT / relative
        target = temp / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return temp


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_current_repository_passes_independent_vol053_verification() -> None:
    receipt = verifier.verify_repository(ROOT)
    assert receipt["valid"] is True, receipt["errors"]
    assert receipt["volume"] == "VOL-053"
    assert receipt["source_contract"]["probe_count"] >= 15
    assert "skeleton.jeeves" in receipt["source_contract"]["probes"]
    assert {
        row["rule_id"]
        for row in receipt["registry_bindings"]
    } == {"ARCH-PYTHON-LAYERS", "ARCH-PACKAGED-WHEEL"}
    assert len(receipt["receipt_digest"]) == 64


def test_rejects_masterplan_packaged_wheel_gap_loss() -> None:
    root = _fixture()
    path = root / verifier.MASTER
    data = _load(path)
    volume = next(item for item in data["volumes"] if item["key"] == "VOL-053")
    volume["gaps"].remove("materialize packaged-wheel import test")
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any("gap binding drift" in error for error in receipt["errors"])


def test_rejects_packaged_wheel_rule_downgrade() -> None:
    root = _fixture()
    path = root / verifier.REGISTRY
    data = _load(path)
    rule = next(
        item
        for item in data["rules"]
        if item["id"] == "ARCH-PACKAGED-WHEEL"
    )
    rule["severity"] = "advisory"
    _write(path, data)

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "ARCH-PACKAGED-WHEEL: severity must remain blocking" == error
        for error in receipt["errors"]
    )


def test_rejects_source_tree_leakage_guard_removal() -> None:
    root = _fixture()
    path = root / verifier.WHEEL_VALIDATOR
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "wheel imports leaked to source tree",
        "source tree leakage ignored",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "wheel isolation invariant missing" in error
        for error in receipt["errors"]
    )


def test_rejects_isolated_mode_removal() -> None:
    root = _fixture()
    path = root / verifier.WHEEL_VALIDATOR
    source = path.read_text(encoding="utf-8")
    source = source.replace('"-I"', '"-c-no-isolation"')
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any('"-I"' in error for error in receipt["errors"])


def test_rejects_path_hack_detection_weakening() -> None:
    root = _fixture()
    path = root / verifier.LAYER_VALIDATOR
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "runtime sys.path/PYTHONPATH mutation is forbidden",
        "runtime path mutation ignored",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "path-hack invariant missing" in error
        for error in receipt["errors"]
    )


def test_rejects_critical_probe_removal() -> None:
    root = _fixture()
    path = root / verifier.WHEEL_VALIDATOR
    source = path.read_text(encoding="utf-8")
    source = source.replace('        "skeleton.jeeves",\n', "")
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        error == "VOL-053 critical wheel probe missing: skeleton.jeeves"
        for error in receipt["errors"]
    )
