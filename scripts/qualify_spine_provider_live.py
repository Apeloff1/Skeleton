#!/usr/bin/env python3
"""Perform one credential-bearing provider call and qualify exact-head P2 evidence.

The script never serializes credentials or model response text. It emits only
identities, bounded timing, and SHA-256/HMAC digests required by the P2 live
provider qualification seam.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

from skeleton.intelligence.admission import ResourceBudget
from skeleton.persistence.spine_provider_live_qualification import (
    SpineProviderLiveQualification,
)
from skeleton.persistence.spine_provider_live_qualification_verify import (
    SpineProviderLiveQualificationVerify,
)
from skeleton.persistence.spine_provider_surface_qualification_verify import (
    SpineProviderSurfaceQualificationVerify,
)
from skeleton.provider_runtime import OpenAIProviderAdapter, ProviderRequest
from skeleton.providers.contract import load_provider_architecture


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _attestation_key(api_key: str) -> bytes:
    return hashlib.sha256(
        b"p2-provider-live-attestation\0" + api_key.encode("utf-8")
    ).digest()


def _attest(receipt: dict[str, Any], key: bytes) -> str:
    payload = {
        name: value
        for name, value in receipt.items()
        if name != "attestation_digest"
    }
    return hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()


def _authenticate(receipt: dict[str, Any], key: bytes) -> bool:
    supplied = receipt.get("attestation_digest")
    return (
        isinstance(supplied, str)
        and len(supplied) == 64
        and hmac.compare_digest(supplied, _attest(receipt, key))
    )


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for live provider qualification")

    closure = json.loads(Path(args.closure).read_text(encoding="utf-8"))
    closure_verify = SpineProviderSurfaceQualificationVerify().verify(closure)
    expected_head = args.expected_head.strip()
    if closure.get("head_sha") != expected_head:
        raise RuntimeError("provider closure is not for the expected head")

    architecture = load_provider_architecture("openai")
    operation_id = "p2-provider-live-" + expected_head[:16]
    model = (args.model or os.environ.get("P2_PROVIDER_LIVE_MODEL") or "").strip()
    adapter = OpenAIProviderAdapter(
        api_key=api_key,
        model=model or None,
        timeout_seconds=float(args.timeout_seconds),
        max_retries=0,
    )
    if not adapter.available:
        raise RuntimeError("canonical OpenAI provider adapter is unavailable")

    request_material = {
        "instructions": "Return exactly the token P2-LIVE.",
        "prompt": "P2 live provider verification. Reply exactly P2-LIVE.",
        "max_output_tokens": 16,
        "model": adapter.model,
        "data_class": "public",
        "purpose": "verification",
        "tenant_id": "p2-provider-live",
        "operation_id": operation_id,
        "head_sha": expected_head,
        "closure_digest": closure["digest"],
    }
    request = ProviderRequest(
        instructions=request_material["instructions"],
        prompt=request_material["prompt"],
        max_output_tokens=request_material["max_output_tokens"],
        model=adapter.model,
        data_class="public",
        purpose="verification",
        tenant_id="p2-provider-live",
        operation_id=operation_id,
        estimated_cost_usd=0.05,
        resource_budget=ResourceBudget(
            max_input_tokens=2_000,
            max_output_tokens=32,
            max_cost_usd=0.25,
            max_wall_seconds=float(args.timeout_seconds) + 5.0,
            max_provider_attempts=1,
            max_tool_calls=0,
            max_artifact_bytes=0,
            max_storage_bytes=0,
            max_concurrency=1,
            max_queue_depth=4,
        ),
    )
    response = await adapter.generate(request)
    if response.provider != "openai":
        raise RuntimeError("live provider response changed provider identity")
    if not isinstance(response.text, str) or not response.text.strip():
        raise RuntimeError("live provider returned no text")
    if not response.request_id or not response.response_id:
        raise RuntimeError("live provider response is missing request identity")

    issued_at = datetime.now(timezone.utc)
    response_material = {
        "provider": response.provider,
        "model": response.model,
        "request_id": response.request_id,
        "response_id": response.response_id,
        "finish_reason": response.finish_reason.value,
        "text_digest": hashlib.sha256(
            response.text.encode("utf-8")
        ).hexdigest(),
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "total_tokens": response.usage.total_tokens,
        },
        "governance_decision_id": response.governance_decision_id,
        "admission_decision_id": response.admission_decision_id,
    }
    latency_ms = int(round(float(response.latency_ms or 0.0)))
    receipt: dict[str, Any] = {
        "kind": "spine_provider_live_receipt",
        "authority_domain": "provider-live",
        "decision": "qualify-live-provider",
        "head_sha": expected_head,
        "closure_digest": closure["digest"],
        "provider_id": response.provider,
        "provider_family": "runtime_model",
        "model": response.model,
        "operation_id": operation_id,
        "request_id": response.request_id,
        "response_id": response.response_id,
        "request_digest": _sha(request_material),
        "response_digest": _sha(response_material),
        "architecture_digest": architecture.contract_digest,
        "latency_ms": latency_ms,
        "issued_at": issued_at.isoformat(),
        "expires_at": (issued_at + timedelta(minutes=5)).isoformat(),
        "success": True,
        "network_transport_used": True,
        "credential_boundary_used": True,
        "architecture_acknowledged": True,
    }
    key = _attestation_key(api_key)
    receipt["attestation_digest"] = _attest(receipt, key)

    card = SpineProviderLiveQualification().qualify(
        closure=closure,
        closure_verify=closure_verify,
        receipt=receipt,
        expected_head_sha=expected_head,
        authenticate=lambda candidate: _authenticate(candidate, key),
        now=issued_at,
    )
    verified = SpineProviderLiveQualificationVerify().verify(card)
    if verified.get("provider_surface_green") is not True:
        raise RuntimeError("live provider qualification did not become green")
    if verified.get("merge_authority") is not False:
        raise RuntimeError("live provider qualification overclaimed merge authority")

    output = {
        "receipt": receipt,
        "qualification": card,
        "verification": verified,
    }
    target = Path(args.evidence_out)
    target.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        "provider-live qualified:",
        expected_head,
        "provider=",
        response.provider,
        "model=",
        response.model,
        "latency_ms=",
        latency_ms,
    )
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--closure", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--evidence-out", required=True)
    parser.add_argument("--model", default="")
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser


def main() -> int:
    args = _parser().parse_args()
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
