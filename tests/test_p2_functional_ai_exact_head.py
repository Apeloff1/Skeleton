from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts.p2_functional_ai_exact_head import (
    ExactHeadReceiptError,
    build_receipt,
    validate_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40


def _clean_env(monkeypatch) -> None:
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "XAI_API_KEY",
        "GOOGLE_API_KEY",
        "AZURE_OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


def test_exact_head_receipt_round_trips_current_surfaces(monkeypatch) -> None:
    _clean_env(monkeypatch)
    receipt = build_receipt(
        ROOT,
        head_sha=HEAD,
        run_id=12345,
        run_attempt=2,
        event_name="pull_request",
    )
    result = validate_receipt(ROOT, receipt, expected_head_sha=HEAD)
    assert result["valid"] is True
    assert result["head_sha"] == HEAD
    assert result["surface_count"] >= 10
    assert receipt["production_local_weights_runtime"]["kind"] == "llama.cpp-cli"
    assert receipt["provider_credentials_present"] is False


def test_exact_head_receipt_rejects_stale_head(monkeypatch) -> None:
    _clean_env(monkeypatch)
    receipt = build_receipt(
        ROOT,
        head_sha=HEAD,
        run_id=1,
        run_attempt=1,
        event_name="pull_request",
    )
    result = validate_receipt(ROOT, receipt, expected_head_sha="b" * 40)
    assert result["valid"] is False
    assert "receipt is not bound to the expected exact head" in result["errors"]


def test_exact_head_receipt_rejects_surface_digest_tamper(monkeypatch) -> None:
    _clean_env(monkeypatch)
    receipt = build_receipt(
        ROOT,
        head_sha=HEAD,
        run_id=1,
        run_attempt=1,
        event_name="push",
    )
    tampered = copy.deepcopy(receipt)
    first = next(iter(tampered["surface_digests"]))
    tampered["surface_digests"][first]["sha256"] = "0" * 64
    result = validate_receipt(ROOT, tampered, expected_head_sha=HEAD)
    assert result["valid"] is False
    assert any("surface digest mismatch" in error for error in result["errors"])
    assert "receipt self-digest mismatch" in result["errors"]


def test_exact_head_receipt_refuses_hosted_provider_credentials(monkeypatch) -> None:
    _clean_env(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-present")
    with pytest.raises(ExactHeadReceiptError, match="credentials are present"):
        build_receipt(
            ROOT,
            head_sha=HEAD,
            run_id=1,
            run_attempt=1,
            event_name="workflow_dispatch",
        )


@pytest.mark.parametrize("head", ["", "abc", "G" * 40, "a" * 39, "a" * 41])
def test_exact_head_receipt_rejects_invalid_head(monkeypatch, head: str) -> None:
    _clean_env(monkeypatch)
    with pytest.raises(ExactHeadReceiptError, match="head_sha"):
        build_receipt(
            ROOT,
            head_sha=head,
            run_id=1,
            run_attempt=1,
            event_name="push",
        )
