from __future__ import annotations

import json
import shutil
from pathlib import Path

from scripts.verify_vol020_multimodal import verify_repository


ROOT = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        "machine/ai_master_plan.json",
        "skeleton/multimodal/contracts.py",
        "skeleton/multimodal/sanitize.py",
        "skeleton/multimodal/ingest.py",
        "skeleton/multimodal/__init__.py",
        "skeleton/ai/runtime/multimodal/contracts.py",
        "skeleton/ai/runtime/multimodal/sanitize.py",
        "skeleton/ai/runtime/multimodal/ingest.py",
        "skeleton/ai/runtime/multimodal/__init__.py",
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return root


def test_independent_vol020_accepts_current_implementation(tmp_path: Path, monkeypatch) -> None:
    root = _fixture(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "vol020-head")
    receipt = verify_repository(root)
    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "vol020-head"
    assert receipt["volume"] == "VOL-020"
    assert receipt["modality_count"] == 5
    assert receipt["checked_invariant_count"] >= 25
    assert len(receipt["source_digests"]) == 4
    assert len(receipt["mirror_digests"]) == 4
    assert len(receipt["volume_binding"]["binding_digest"]) == 64
    assert len(receipt["receipt_digest"]) == 64


def test_independent_vol020_rejects_source_mirror_drift(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    mirror = root / "skeleton/ai/runtime/multimodal/sanitize.py"
    mirror.write_text(mirror.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "VOL-020 source/AI mirror drift: sanitize.py" in receipt["errors"]


def test_independent_vol020_rejects_authority_escalation_boundary_removal(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/multimodal/contracts.py",
        "skeleton/ai/runtime/multimodal/contracts.py",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8").replace(
            "media cannot grant policy authority",
            "media may grant policy authority",
        )
        path.write_text(text, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("media cannot grant policy authority" in error for error in receipt["errors"])


def test_independent_vol020_rejects_hidden_instruction_quarantine_removal(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/multimodal/sanitize.py",
        "skeleton/ai/runtime/multimodal/sanitize.py",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8").replace(
            "embedded-instruction",
            "embedded-content",
        )
        path.write_text(text, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("embedded-instruction" in error for error in receipt["errors"])


def test_independent_vol020_rejects_quarantine_payload_preservation(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/multimodal/sanitize.py",
        "skeleton/ai/runtime/multimodal/sanitize.py",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8").replace(
            'safe=b"" if quarantined else payload',
            "safe=payload",
        )
        path.write_text(text, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any('safe=b"" if quarantined else payload' in error for error in receipt["errors"])


def test_independent_vol020_rejects_missing_plan_binding(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "machine/ai_master_plan.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    volume = next(row for row in data["volumes"] if row["key"] == "VOL-020")
    volume["tests"].remove("skeleton/testing/test_vol020_multimodal_ingest.py")
    path.write_text(json.dumps(data), encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("test binding incomplete" in error for error in receipt["errors"])


def test_independent_vol020_rejects_modality_loss(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    for relative in (
        "skeleton/multimodal/contracts.py",
        "skeleton/ai/runtime/multimodal/contracts.py",
    ):
        path = root / relative
        text = path.read_text(encoding="utf-8").replace('VIDEO="video"', 'VIDEO="moving-image"')
        path.write_text(text, encoding="utf-8")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("modality coverage drift" in error for error in receipt["errors"])
