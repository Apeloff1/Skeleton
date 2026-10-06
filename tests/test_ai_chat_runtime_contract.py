from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_ai_chat_runtime.py"
VERIFY = ROOT / "scripts" / "verify_ai_chat_runtime.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ai_chat_runtime_contract_is_structurally_valid() -> None:
    checker = _load(CHECK, "check_ai_chat_runtime")
    assert checker.validate() == []


def test_exact_head_evidence_is_independently_rehashed(tmp_path: Path) -> None:
    checker = _load(CHECK, "check_ai_chat_runtime_evidence")
    verifier = _load(VERIFY, "verify_ai_chat_runtime")
    head = "1" * 40
    receipt = checker.evidence(head)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    result = verifier.verify(receipt_path, head)
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["expected_head"] == head
    assert result["structural_evidence_digest"] == result[
        "recomputed_structural_evidence_digest"
    ]
    assert len(result["contract_digest"]) == 64
    assert len(result["receipt_digest"]) == 64
    assert len(result["verifier_digest"]) == 64
    assert len(result["file_digests"]) == 7


def test_independent_rehasher_rejects_wrong_head(tmp_path: Path) -> None:
    checker = _load(CHECK, "check_ai_chat_runtime_wrong_head")
    verifier = _load(VERIFY, "verify_ai_chat_runtime_wrong_head")
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(checker.evidence("2" * 40), sort_keys=True),
        encoding="utf-8",
    )

    result = verifier.verify(receipt_path, "3" * 40)
    assert result["valid"] is False
    assert "structural receipt is not exact-head" in result["errors"]
