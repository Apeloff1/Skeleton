from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "check_advanced_ai_structure.py"
VERIFIER = ROOT / "scripts" / "verify_advanced_ai_structure.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payloads():
    return {
        "contract": json.loads(
            (ROOT / "machine" / "advanced_ai_structure_100.json").read_text(
                encoding="utf-8"
            )
        ),
        "construction": json.loads(
            (ROOT / "machine" / "ai_app_construction.json").read_text(
                encoding="utf-8"
            )
        ),
        "enterprise": json.loads(
            (ROOT / "machine" / "enterprise_system_architecture.json").read_text(
                encoding="utf-8"
            )
        ),
    }


def _validate(checker, payloads):
    return checker.validate_payloads(
        payloads["contract"],
        payloads["construction"],
        payloads["enterprise"],
        repo_root=ROOT,
    )


def test_advanced_ai_structure_is_valid() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker")
    assert checker.validate() == []


def test_exactly_100_contiguous_levels_and_ten_strata() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_counts")
    payloads = _payloads()
    contract = payloads["contract"]
    assert [level["ordinal"] for level in contract["levels"]] == list(
        range(1, 101)
    )
    assert [level["id"] for level in contract["levels"]] == [
        f"L{i:03d}" for i in range(1, 101)
    ]
    assert len(contract["strata"]) == 10
    assert _validate(checker, payloads) == []


def test_missing_level_fails_closed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_missing")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"].pop(44)
    errors = _validate(checker, payloads)
    assert "advanced AI structure must contain exactly 100 levels" in errors
    assert "advanced level IDs must be exactly L001 through L100" in errors


def test_forward_promotion_dependency_fails_closed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_forward")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"][49]["promotion_prerequisites"] = ["L051"]
    errors = _validate(checker, payloads)
    assert "L050 must promote from exactly L049" in errors
    assert "L050 prerequisite must point backward: L051" in errors


def test_unknown_plane_fails_closed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_plane")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["strata"][0]["planes"].append("shadow-cognition")
    payloads["contract"]["levels"][0]["required_planes"].append(
        "shadow-cognition"
    )
    errors = _validate(checker, payloads)
    assert any("references unknown planes" in error for error in errors)


def test_every_tenth_level_is_gate_and_only_every_tenth() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_gate")
    payloads = _payloads()
    for level in payloads["contract"]["levels"]:
        assert level["gate"] is (level["ordinal"] % 10 == 0)
    assert _validate(checker, payloads) == []


def test_planning_change_cannot_pre_promote_or_sign_levels() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_promotion")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["completion"]["promoted_levels"] = ["L001"]
    payloads["contract"]["completion"]["signed_levels"] = ["L001"]
    errors = _validate(checker, payloads)
    assert "planning change must not pre-promote levels" in errors
    assert "planning change must not pre-sign levels" in errors


def test_level_99_and_100_guardrails_are_fixed() -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_frontier")
    payloads = _payloads()
    payloads["contract"] = copy.deepcopy(payloads["contract"])
    payloads["contract"]["levels"][98]["title"] = "Unbounded Self Evolution"
    payloads["contract"]["levels"][99]["title"] = "Automatic Self Approval"
    errors = _validate(checker, payloads)
    assert "L099 must preserve bounded self-evolution governance" in errors
    assert "L100 must remain Frontier System Acceptance" in errors


def test_structural_receipt_independently_rehashes(tmp_path: Path) -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_receipt")
    verifier = _load_module(VERIFIER, "advanced_ai_verifier")
    head = "a" * 40
    receipt = checker.evidence(head)
    path = tmp_path / "receipt.json"
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = verifier.verify(path, head)
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["level_count"] == 100
    assert result["stratum_count"] == 10
    assert result["implementation_claim"] is False
    assert result["structural_evidence_digest"] == (
        result["recomputed_structural_evidence_digest"]
    )


def test_independent_verifier_rejects_tampered_receipt(tmp_path: Path) -> None:
    checker = _load_module(CHECKER, "advanced_ai_checker_tamper")
    verifier = _load_module(VERIFIER, "advanced_ai_verifier_tamper")
    head = "b" * 40
    receipt = checker.evidence(head)
    first = next(iter(receipt["file_digests"]))
    receipt["file_digests"][first] = "0" * 64
    path = tmp_path / "tampered.json"
    path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = verifier.verify(path, head)
    assert result["valid"] is False
    assert "advanced AI independent file digest map mismatch" in result["errors"]
    assert "advanced AI evidence digest mismatch" in result["errors"]
