"""Canonical enterprise dossier regeneration is evidence-preserving and idempotent."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reconcile_enterprise_ai_implementation_notes.py"


def _module():
    spec = importlib.util.spec_from_file_location("reconcile_enterprise_ai_implementation_notes", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _master():
    source = {
        "key": "VOL-000", "title": "Canonical source", "depth_pass": "DP-000-040",
        "implementation_status": "verified",
        "enterprise_grade_state": "designed", "enterprise_grade_target": "enterprise_qualified",
    }
    for key in (
        "requirements", "capabilities", "contracts", "implementation_paths",
        "risks", "gaps", "tests", "evaluations", "evidence",
    ):
        source[key] = [f"{key}-{i}" for i in range(10)]
    return source


def _dossier():
    return {
        "volume_ref": "VOL-000", "title": "old title",
        "enterprise_grade_state": "designed",
        "implementation_summary": {key: [] for key in _module().FIELDS},
        "implementation_levels": [{"id": "L13", "evidence": "separate evaluation pending"}],
        "evidence_policy": ["independent verifier only"],
        "completion_rule": "no self-signing",
        "signed_by": None,
    }


def test_projection_updates_only_fields_owned_by_authoritative_master():
    module = _module()
    dossier = _dossier()
    a, b = module.project_dossier(dossier, _master())
    assert a == len(module.FIELDS)
    assert b > 0
    assert dossier["implementation_summary"]["existing_evidence"] == [
        f"evidence-{i}" for i in range(8)
    ]
    assert dossier["legacy_implementation_status"] == "verified"
    assert dossier["signed_by"] is None
    assert dossier["completion_rule"] == "no self-signing"
    assert dossier["implementation_levels"] == [
        {"id": "L13", "evidence": "separate evaluation pending"}
    ]
    assert dossier["evidence_policy"] == ["independent verifier only"]
    assert module.project_dossier(dossier, _master()) == (0, 0)


def test_projection_rejects_wrong_source_or_missing_canonical_arrays():
    module = _module()
    other = _master()
    other["key"] = "VOL-001"
    with pytest.raises(module.DossierReconciliationError, match="another volume"):
        module.project_dossier(_dossier(), other)
    malformed = _master()
    del malformed["evidence"]
    with pytest.raises(module.DossierReconciliationError, match="source evidence"):
        module.project_dossier(_dossier(), malformed)


def test_live_dossiers_are_current_without_implicit_write():
    module = _module()
    receipt = module.reconcile(ROOT, write=False)
    assert receipt["volume_count"] == 421
    assert receipt["current"] is True
    assert receipt["changed_files"] == []
    assert receipt["summary_changes"] == 0
    assert receipt["metadata_changes"] == 0
    assert receipt["write_performed"] is False
