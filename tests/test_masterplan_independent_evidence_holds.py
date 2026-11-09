"""Independent evidence stays mandatory for the deferred masterplan lanes.

This checks source truth, never asserts implementation completeness from a
planned test path or documentation link.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "machine/ai_master_plan.json"


def _read(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_candidate_volumes_cannot_self_qualify_independent_verification():
    master = _read("machine/ai_master_plan.json")
    security = _read("machine/ai_security_governance_gapfill_candidate.json")
    economics = _read("machine/ai_observability_economics_gapfill_candidate.json")
    policy = _read("machine/manifest_reference_policy.json")
    selected = set(security["volume_refs"]) | set(economics["volume_refs"]) | {"VOL-054"}
    volumes = {v["key"]: v for v in master["volumes"]}
    assert selected <= set(volumes)

    for key in selected:
        volume = volumes[key]
        assert volume["implementation_status"] == "implemented", key
        assert volume["completion_checkbox"] is False, key
        assert volume["completion_checkbox_mark"] == "[ ]", key
        assert volume["gaps"] and all(isinstance(s, str) and s.strip() for s in volume["gaps"])
        # Existing functional evidence is kept but cannot independently close a
        # separate governance verification obligation.
        assert isinstance(volume["evidence"], list), key

    assert policy["masterplan_binding"]["required_gap_texts"] == volumes["VOL-054"]["gaps"]


def test_manifest_binding_is_exact_git_blob_identical_to_human_authority():
    import hashlib

    data = (ROOT / "machine/manifest_reference_policy.json").read_bytes()
    blob = hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()
    doc = (ROOT / "docs/architecture/MANIFEST_REFERENCE_INTEGRITY.md").read_text(encoding="utf-8")
    assert doc.count("machine-git-blob: machine/manifest_reference_policy.json@") == 1
    assert f"machine-git-blob: machine/manifest_reference_policy.json@{blob}" in doc
