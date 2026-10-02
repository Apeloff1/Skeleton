from __future__ import annotations

from dataclasses import replace
import json

import pytest

from skeleton.ai.evaluation.system_qualification import qualify_system_completion
from skeleton.ai.runtime.system_completion import REQUIRED_COMPLETION_REQUIREMENTS


HEAD = "d" * 40


@pytest.mark.asyncio
async def test_executable_system_qualification_emits_seventeen_exact_revision_proofs(
    tmp_path,
) -> None:
    receipt = await qualify_system_completion(
        tmp_path,
        source_revision=HEAD,
    )

    assert receipt.valid is True
    assert receipt.source_revision == HEAD
    assert receipt.report.valid is True
    assert receipt.report.missing == ()
    assert receipt.report.failed == ()
    assert len(receipt.report.proofs) == len(REQUIRED_COMPLETION_REQUIREMENTS) == 17
    assert receipt.network_attempt_count == 0
    assert receipt.primary_result_digest == receipt.replay_result_digest
    assert receipt.primary_output_digest == receipt.replay_output_digest
    assert receipt.observed_tool_ids == ("repo.read",)
    assert receipt.replay_observed_tool_ids == receipt.observed_tool_ids
    assert all(proof.source_revision == HEAD for proof in receipt.report.proofs)
    assert all(proof.subject_id == receipt.subject_id for proof in receipt.report.proofs)
    assert len(receipt.digest) == 64

    payload = receipt.as_dict()
    assert payload["valid"] is True
    assert payload["report"]["valid"] is True
    assert payload["report"]["source_revision"] == HEAD
    assert len(payload["report"]["proofs"]) == 17
    assert all(
        proof["source_revision"] == HEAD
        for proof in payload["report"]["proofs"]
    )


@pytest.mark.asyncio
async def test_qualification_receipt_rejects_replay_digest_divergence(
    tmp_path,
) -> None:
    receipt = await qualify_system_completion(
        tmp_path,
        source_revision=HEAD,
    )
    divergent = replace(
        receipt,
        replay_result_digest="0" * 64,
    )
    assert divergent.valid is False
    assert divergent.digest != receipt.digest


@pytest.mark.asyncio
async def test_qualification_receipt_is_canonical_json(
    tmp_path,
) -> None:
    receipt = await qualify_system_completion(
        tmp_path,
        source_revision=HEAD,
    )
    encoded = json.dumps(
        receipt.as_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    decoded = json.loads(encoded)
    assert decoded["digest"] == receipt.digest
    assert decoded["report"]["digest"] == receipt.report.digest
