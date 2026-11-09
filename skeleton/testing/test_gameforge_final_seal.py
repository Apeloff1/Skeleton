"""Final ledger and build report are written after seal, never during emit."""
from __future__ import annotations
import json
from pathlib import Path
import pytest
from skeleton.context.cockpit import Cockpit
from skeleton.context.pipeline import _stage_seal

def test_final_seal_writes_truthful_manifests_and_ledger(tmp_path):
    cockpit = Cockpit()
    ctx = {
        "cockpit": cockpit, "era": "cozy_wholesome",
        "project": {"root": str(tmp_path)},
        "build_plan": {"seed": "seed-42"},
        "oracle_text": "Preserve tranquility",
        "files": {"project.godot": "[application]\n", "data/rooms.json": "{}"},
        "sim": {"passed": True},
        "playtest": {"status": "passed"},
    }
    result = _stage_seal(ctx)
    assert result["sealed"] is True
    report = (tmp_path / "build_report.md").read_text(encoding="utf-8")
    assert "seed-42" in report
    assert "Preserve tranquility" in report
    assert "unmeasured" in report
    assert result["build_report"]["manifest_sha256"] in report
    ledger = json.loads((tmp_path / "CONTEXT_LEDGER.json").read_text())
    tensor = json.loads((tmp_path / "CONTEXT_TENSOR.json").read_text())
    assert ledger["valid"] is True
    assert ledger["blocks"][-1]["stage"] == "seal"
    assert ledger["head"] == result["build_report"]["ledger_head"]
    assert tensor["era"] == "extraction_now"

def test_corrupt_preseal_ledger_fails_without_final_report(tmp_path):
    cockpit = Cockpit()
    cockpit.ledger.tamper(0, "note", "tampered")
    with pytest.raises(RuntimeError, match="pre-seal ledger"):
        _stage_seal({"cockpit": cockpit, "era": "soulslike",
                     "project": {"root": str(tmp_path)}})
    assert not (tmp_path / "build_report.md").exists()

def test_in_memory_api_seal_never_writes_file():
    cockpit = Cockpit()
    result = _stage_seal({"cockpit": cockpit, "era": "cozy_wholesome", "project": None})
    assert result["sealed"] is True
    assert result["build_report"] is None


def test_existing_evidence_symlink_does_not_redirect_seal_output(tmp_path):
    outside = tmp_path / "outside"
    outside.write_text("untouched", encoding="utf-8")
    (tmp_path / "build_report.md").symlink_to(outside)
    cockpit = Cockpit()
    with pytest.raises(ValueError, match="symlink"):
        _stage_seal({"cockpit": cockpit, "era": "cozy_wholesome",
                     "project": {"root": str(tmp_path)}, "files": {
                         "project.godot": "[application]"
                     }})
    assert outside.read_text(encoding="utf-8") == "untouched"
    assert not (tmp_path / "CONTEXT_LEDGER.json").exists()
    assert not (tmp_path / "CONTEXT_TENSOR.json").exists()
