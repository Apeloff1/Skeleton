from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.verify_vol006_model_development import verify_repository


ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/ai_master_plan.json",
        "skeleton/modeling/registry.py",
        "skeleton/modeling/training.py",
        "skeleton/modeling/evaluation.py",
        "skeleton/modeling/publication.py",
        "skeleton/ai/modeling/registry.py",
        "skeleton/ai/modeling/training.py",
        "skeleton/ai/modeling/evaluation.py",
        "skeleton/ai/modeling/publication.py",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_independent_vol006_accepts_current_implementation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _fixture(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "vol006-head")
    receipt = verify_repository(root)
    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "vol006-head"
    assert receipt["volume"] == "VOL-006"
    assert receipt["checked_invariant_count"] >= 40
    assert len(receipt["source_digests"]) == 4
    assert len(receipt["mirror_digests"]) == 4
    assert len(receipt["volume_binding"]["binding_digest"]) == 64
    assert len(receipt["receipt_digest"]) == 64


def test_independent_vol006_rejects_registry_mirror_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    mirror = root / "skeleton/ai/modeling/registry.py"
    mirror.write_text(
        mirror.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "VOL-006 source/AI mirror drift: registry.py" in receipt["errors"]


def test_independent_vol006_rejects_dataset_governance_weakening(
    tmp_path: Path,
) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/modeling/registry.py",
        "skeleton/ai/modeling/registry.py",
    ):
        path = root / relative
        source = path.read_text(encoding="utf-8").replace(
            "contamination_digest",
            "quality_digest",
        )
        path.write_text(source, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("contamination_digest" in error for error in receipt["errors"])


def test_independent_vol006_rejects_production_authority_escalation(
    tmp_path: Path,
) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/modeling/publication.py",
        "skeleton/ai/modeling/publication.py",
    ):
        path = root / relative
        source = path.read_text(encoding="utf-8").replace(
            "completion cannot grant production authority",
            "completion may grant production authority",
        )
        path.write_text(source, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any(
        "completion cannot grant production authority" in error
        for error in receipt["errors"]
    )


def test_independent_vol006_rejects_training_recovery_weakening(
    tmp_path: Path,
) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/modeling/training.py",
        "skeleton/ai/modeling/training.py",
    ):
        path = root / relative
        source = path.read_text(encoding="utf-8").replace(
            "checkpoint state mismatch",
            "checkpoint mismatch ignored",
        )
        path.write_text(source, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("checkpoint state mismatch" in error for error in receipt["errors"])


def test_independent_vol006_rejects_masterplan_binding_drift(
    tmp_path: Path,
) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-006")
    volume["tests"].remove("skeleton/testing/test_vol006_model_registry.py")
    _write(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("VOL-006 test binding incomplete" in error for error in receipt["errors"])


def test_independent_vol006_rejects_gap_clear_without_signoff(
    tmp_path: Path,
) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-006")
    volume["gaps"] = []
    volume["completion_checkbox"] = False
    volume["completion_checkbox_mark"] = "[ ]"
    _write(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "VOL-006 cannot clear qualification gap before signoff" in receipt["errors"]


def test_independent_vol006_accepts_signed_state(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = _load(path)
    volume = next(row for row in payload["volumes"] if row["key"] == "VOL-006")
    volume["gaps"] = []
    volume["completion_checkbox"] = True
    volume["completion_checkbox_mark"] = "[x]"
    volume["implementation_status"] = "verified"
    _write(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is True
    assert receipt["errors"] == []
