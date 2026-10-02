from __future__ import annotations

import json

import pytest

from scripts.verify_ai_system_qualification_receipt import verify_receipt
from skeleton.ai.evaluation.system_qualification import (
    qualify_system_completion,
)


HEAD = "e" * 40


async def _write_receipt(tmp_path):
    receipt = await qualify_system_completion(
        tmp_path,
        source_revision=HEAD,
    )
    path = tmp_path / "qualification.json"
    path.write_text(
        json.dumps(receipt.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt, path


@pytest.mark.asyncio
async def test_independent_verifier_rehashes_complete_receipt(
    tmp_path,
) -> None:
    receipt, path = await _write_receipt(tmp_path)

    verdict = verify_receipt(path, expected_head=HEAD)

    assert receipt.valid is True
    assert verdict["valid"] is True
    assert verdict["errors"] == []
    assert verdict["receipt_digest"] == receipt.digest
    assert len(verdict["contract_digest"]) == 64
    assert len(verdict["verifier_digest"]) == 64


@pytest.mark.asyncio
async def test_independent_verifier_rejects_tampered_proof_details(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["report"]["proofs"][0]["details"]["tampered"] = True
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert any(
        "proof digest mismatch" in error
        for error in verdict["errors"]
    )


@pytest.mark.asyncio
async def test_independent_verifier_rejects_reordered_proofs(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["report"]["proofs"] = list(
        reversed(payload["report"]["proofs"])
    )
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert any(
        "canonical requirement order" in error
        for error in verdict["errors"]
    )


@pytest.mark.asyncio
async def test_independent_verifier_rejects_forged_receipt_digest(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["digest"] = "0" * 64
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert "qualification receipt digest mismatch" in verdict["errors"]


@pytest.mark.asyncio
async def test_independent_verifier_rejects_wrong_head(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)

    verdict = verify_receipt(
        path,
        expected_head="f" * 40,
    )

    assert verdict["valid"] is False
    assert "not exact-head" in verdict["errors"][0]


@pytest.mark.asyncio
async def test_independent_verifier_rejects_duplicate_json_keys(
    tmp_path,
) -> None:
    _receipt, path = await _write_receipt(tmp_path)
    encoded = path.read_text(encoding="utf-8")
    needle = f'"source_revision": "{HEAD}"'
    encoded = encoded.replace(
        needle,
        f'{needle},\n  "source_revision": "{HEAD}"',
        1,
    )
    path.write_text(encoded, encoding="utf-8")

    verdict = verify_receipt(path, expected_head=HEAD)

    assert verdict["valid"] is False
    assert "duplicate JSON object key" in verdict["errors"][0]
