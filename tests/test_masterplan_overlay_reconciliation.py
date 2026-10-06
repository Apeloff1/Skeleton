from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/check_masterplan_overlay_reconciliation.py"

def _module():
    spec = importlib.util.spec_from_file_location("overlay_reconciliation", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def test_overlay_reconciliation_contract_passes():
    result = _module().validate()
    assert result["ok"] is True
    assert result["required_json_authorities"] >= 20
    assert result["required_human_authorities"] >= 11

def test_git_blob_sha_matches_git_object_format():
    mod = _module()
    assert mod._git_blob_sha(b"test\n") == "9daeafb9864cf43055ae93beb0afd6c7d144bfa4"
