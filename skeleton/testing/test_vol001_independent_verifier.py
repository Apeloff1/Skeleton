from __future__ import annotations
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts" / "verify_vol001_research_closure.py"
SPEC = importlib.util.spec_from_file_location("vol001_verifier", PATH)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

def test_receipt_is_exact_head_bound_authority_neutral_and_deterministic():
    head = "a" * 40
    first = MOD.build_receipt(head, actual_head_sha=head)
    second = MOD.build_receipt(head, actual_head_sha=head)
    assert first == second
    assert first["head_sha"] == head
    assert first["valid"] is True
    assert first["authority_scope"] == "verification-evidence-only"
    assert first["production_authority"] is False
    assert first["completion_authority"] is False
    assert len(first["evidence_digest"]) == 64

def test_receipt_fails_closed_on_invalid_head_identity():
    receipt = MOD.build_receipt("main", actual_head_sha="a" * 40)
    assert receipt["valid"] is False
    assert receipt["errors"]
    assert receipt["completion_authority"] is False

def test_receipt_binds_canonical_mirror_and_regression_digests():
    receipt = MOD.build_receipt("b" * 40, actual_head_sha="b" * 40)
    assert set(receipt["mirror_digests"]) == {pair[0] for pair in MOD.PAIRS}
    assert set(receipt["test_digests"]) == set(MOD.TESTS)
    for values in receipt["mirror_digests"].values():
        assert values["canonical_digest"] == values["mirror_digest"]

def test_receipt_rejects_valid_but_mismatched_repository_head():
    declared = "c" * 40
    actual = "d" * 40
    receipt = MOD.build_receipt(declared, actual_head_sha=actual)
    assert receipt["valid"] is False
    assert receipt["repository_head_sha"] == actual
    assert "declared head_sha does not match checked-out repository HEAD" in receipt["errors"]
