from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


HEAD = "a" * 40


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _closure() -> dict[str, object]:
    evidence = {
        "head_sha": HEAD,
        "canonical_receipt_digest": "1" * 64,
        "independent_receipt_digest": "2" * 64,
        "declared_digest": "3" * 64,
        "independent_declared_surface_digest": "4" * 64,
        "discovered_digest": "5" * 64,
        "declared_count": 1,
        "discovered_count": 1,
        "scanned_python_files": 2,
        "exact_head": True,
        "independent_agreement": True,
        "provider_surface_closure_green": True,
        "provider_surface_live_green": False,
        "provider_surface_green": False,
        "pr_automation_green": False,
    }
    return {
        "kind": "spine_provider_surface_qualification",
        "hit": True,
        "law": "paired-exact-head-receipts-qualify-provider-closure",
        "citation": "VOL-134",
        **evidence,
        "digest": _digest(evidence),
        "stored_prose": 0,
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }


def _load_script():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "qualify_spine_provider_live.py"
    spec = importlib.util.spec_from_file_location(
        "qualify_spine_provider_live_test_target",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeAdapter:
    def __init__(self, **kwargs):
        self.model = kwargs.get("model") or "test-model"
        self.available = True

    async def generate(self, request):
        assert request.data_class == "public"
        assert request.purpose == "verification"
        return SimpleNamespace(
            text="very-sensitive-response-text",
            provider="openai",
            model=self.model,
            request_id="req-live-1",
            response_id="resp-live-1",
            finish_reason=SimpleNamespace(value="completed"),
            usage=SimpleNamespace(
                input_tokens=11,
                output_tokens=3,
                total_tokens=14,
            ),
            latency_ms=12.4,
            governance_decision_id="gov-live",
            admission_decision_id="adm-live",
        )


def test_live_provider_script_emits_only_non_secret_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    monkeypatch.setenv("OPENAI_API_KEY", "SECRET_API_KEY_VALUE")
    monkeypatch.setenv(
        "P2_PROVIDER_LIVE_ATTESTATION_KEY",
        "SECRET_ATTESTATION_VALUE",
    )
    monkeypatch.setattr(module, "OpenAIProviderAdapter", _FakeAdapter)
    monkeypatch.setattr(
        module,
        "load_provider_architecture",
        lambda provider_id: SimpleNamespace(contract_digest="f" * 64),
    )

    closure_path = tmp_path / "closure.json"
    evidence_path = tmp_path / "live.json"
    closure_path.write_text(
        json.dumps(_closure(), sort_keys=True),
        encoding="utf-8",
    )
    args = argparse.Namespace(
        closure=str(closure_path),
        expected_head=HEAD,
        evidence_out=str(evidence_path),
        model="test-model",
        timeout_seconds=5.0,
    )
    output = asyncio.run(module._run(args))

    raw = evidence_path.read_text(encoding="utf-8")
    assert "SECRET_API_KEY_VALUE" not in raw
    assert "SECRET_ATTESTATION_VALUE" not in raw
    assert "very-sensitive-response-text" not in raw
    assert output["receipt"]["success"] is True
    assert output["receipt"]["network_transport_used"] is True
    assert output["qualification"]["provider_surface_green"] is True
    assert output["qualification"]["merge_authority"] is False
    assert output["verification"]["verified"] is True


def test_live_provider_script_requires_separate_attestation_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_script()
    monkeypatch.delenv("P2_PROVIDER_LIVE_ATTESTATION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ATTESTATION_KEY is required"):
        module._attestation_key()
