"""Text-to-telemetry cycle over the serving/tokenizer fence.

Prompt length is taken from the tokenizer, not from the caller. Telemetry is
recorded only after observe succeeds. A counter whose digest drifts from the
bound identity cannot open a plan. No execution authority.

Parent #80. stored_prose=0.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Protocol

from .serving_telemetry import RequestTelemetry, ServingTelemetryWindow
from .serving_token_synergy import JointReceipt, ServingTokenSynergy, SynergyError
from .slo_planner import SLOTarget

SCHEMA = "skeleton.ai.serving-token-cycle.v1"


class TokenCounter(Protocol):
    digest: str

    def encode_ids(self, text: str) -> tuple[int, ...]:
        """Return token ids. Must not admit a mutated vocabulary."""


@dataclass(frozen=True, slots=True)
class CycleCard:
    request_id: str
    prompt_tokens: int
    admitted: bool
    reason: str
    tokenizer_digest: str
    receipt_digest: str

    def card(self) -> dict[str, object]:
        return {
            "kind": "serving-token-cycle",
            "schema": SCHEMA,
            "parent": "#80",
            "hit": 1 if self.admitted else 0,
            "law": self.reason,
            "citation": "docs/lineage/serving_token_synergy.md",
            "stored_prose": 0,
            "request_id": self.request_id,
            "prompt_tokens": self.prompt_tokens,
            "tokenizer_digest": self.tokenizer_digest,
            "digest": self.receipt_digest,
        }


class ServingTokenCycle:
    def __init__(
        self,
        synergy: ServingTokenSynergy,
        counter: TokenCounter,
        window: ServingTelemetryWindow | None = None,
    ) -> None:
        if not isinstance(synergy, ServingTokenSynergy):
            raise SynergyError("ServingTokenSynergy required")
        if not hasattr(counter, "encode_ids") or not isinstance(getattr(counter, "digest", None), str):
            raise SynergyError("token counter required")
        if window is None:
            window = ServingTelemetryWindow(max_records=256)
        if not isinstance(window, ServingTelemetryWindow):
            raise SynergyError("ServingTelemetryWindow required")
        self.synergy = synergy
        self.counter = counter
        self.window = window

    def admit_text(
        self,
        *,
        request_id: str,
        text: str,
        slo: SLOTarget,
        kv_capacity_bytes: int,
        kv_used_bytes: int,
        queue_pressure_pct: int,
    ) -> JointReceipt:
        self._require_counter()
        if not isinstance(text, str):
            raise SynergyError("text must be a string")
        ids = self.counter.encode_ids(text)
        prompt_tokens = self._count(ids)
        return self.synergy.admit(
            request_id=request_id,
            prompt_tokens=prompt_tokens,
            slo=slo,
            kv_capacity_bytes=kv_capacity_bytes,
            kv_used_bytes=kv_used_bytes,
            queue_pressure_pct=queue_pressure_pct,
            tokenizer_digest=self.counter.digest,
        )

    def observe_and_record(
        self,
        telemetry: RequestTelemetry,
        *,
        kv_bytes_per_token: int,
        admission_digest: str,
    ) -> JointReceipt:
        self._require_counter()
        if not isinstance(telemetry, RequestTelemetry):
            raise SynergyError("RequestTelemetry required")
        if telemetry.request_id in self.window._records:
            raise SynergyError("telemetry already recorded")
        if len(self.window._records) >= self.window.max_records:
            raise SynergyError("telemetry window full")
        receipt = self.synergy.observe(
            telemetry,
            kv_bytes_per_token=kv_bytes_per_token,
            tokenizer_digest=self.counter.digest,
            admission_digest=admission_digest,
        )
        self.window.record(telemetry)
        return receipt

    def cohort(self, slo: SLOTarget) -> dict[str, object]:
        if not isinstance(slo, SLOTarget):
            raise SynergyError("SLOTarget required")
        self._require_counter()
        metrics = self.window.metrics(
            ttft_slo_ms=slo.ttft_ms,
            inter_token_slo_ms=slo.inter_token_ms,
            e2e_slo_ms=slo.end_to_end_ms,
        )
        body = {
            "schema": SCHEMA,
            "tokenizer_digest": self.synergy.identity.digest,
            "telemetry_digest": metrics["digest"],
            "requests": metrics["requests"],
            "record_digest": metrics["record_digest"],
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {**body, "digest": digest, "stored_prose": 0, "merge_authority": 0, "parent": "#80"}

    def _require_counter(self) -> None:
        digest = self.counter.digest
        if not hmac.compare_digest(digest, self.synergy.identity.digest):
            raise SynergyError("tokenizer identity drift")

    def _count(self, ids: object) -> int:
        if isinstance(ids, (str, bytes)) or not isinstance(ids, tuple):
            raise SynergyError("encoder must return a token tuple")
        if any(type(token) is not int or token < 0 for token in ids):
            raise SynergyError("encoder returned a non-token")
        return len(ids)


__all__ = ["CycleCard", "ServingTokenCycle", "TokenCounter"]
