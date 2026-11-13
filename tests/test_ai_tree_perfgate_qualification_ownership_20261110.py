"""Exact Git-root retain/owner regression for independent performance qualification.

The added packages are neither AI model execution owners nor source cutover
signoffs; their namespace and full retained-root count stay auditable.
"""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
PATHS = {"skeleton/perfgate", "skeleton/qualification"}


def test_non_ai_performance_owners_are_explicit_and_real():
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    retained = manifest["retained_outside_ai_tree"]
    for path in sorted(PATHS):
        matches = [row for row in retained if row.get("path") == path]
        assert len(matches) == 1
        assert matches[0].get("owner")
        assert matches[0].get("reason")
        assert (ROOT / path).is_dir()
        assert not any(row["source"] == path for row in manifest["mappings"])


def test_readiness_count_and_cutover_signoff_remain_fail_closed():
    manifest = json.loads((ROOT / "machine/ai_file_tree.json").read_text(encoding="utf-8"))
    assert manifest["pre_move_readiness"]["retained_outside_ai_tree_count"] == len(
        manifest["retained_outside_ai_tree"]
    )
    assert manifest["implementation_signoff"]["signed"] is False
    assert manifest["verification_signoff"]["signed"] is False
    assert manifest["pre_move_readiness"]["fresh_object_audit_required"] is True
