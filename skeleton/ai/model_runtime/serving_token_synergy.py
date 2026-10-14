"""Joint admission between tokenizer identity and closed-loop serving.

A serving plan must not be replayed under a different tokenizer digest, and a
feedback observation must not train the estimator unless that request was
admitted under the same identity. This module grants no execution authority.

Parent cite: #80. stored_prose=0.
Composes #3537 serving fence with #3535 tokenizer checkpoint law.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
from typing import Mapping

from .closed_loop_serving import ClosedLoopServingController, ControlDecision
from .runtime_feedback import DeterministicRuntimeEstimator
from .serving_telemetry import RequestTelemetry
from .slo_planner import SLOTarget

PACKET = "SERVE-TOKEN-SYNERGY-20261008"
PARENT = "#80"
STORED_PROSE = 0
SCHEMA = "skeleton.ai.serving-token-synergy.v1"
_HEX = set("0123456789abcdef")


class SynergyError(ValueError):
    """Fail-closed joint admission rejection."""


def _hex64(value: object, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise SynergyError(f"invalid {label}")
    return value


def _pos_int(value: object, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise SynergyError(f"positive integer {label} required")
    return value


@dataclass(frozen=True, slots=True)
class TokenizerIdentity:
    """Frozen tokenizer admission facts. Not a live model handle."""

    digest: str
    vocab_size: int
    unk: int
    checkpoint_schema: str = "skeleton.ai.tokenizer-checkpoint.v1"

    def __post_init__(self) -> None:
        _hex64(self.digest, "tokenizer digest")
        _pos_int(self.vocab_size, "vocab_size")
        if type(self.unk) is not int or not 0 <= self.unk < self.vocab_size:
            raise SynergyError("unk outside vocabulary")
        if not isinstance(self.checkpoint_schema, str) or not self.checkpoint_schema:
            raise SynergyError("checkpoint schema required")


@dataclass(frozen=True, slots=True)
class JointReceipt:
    request_id: str
    admitted: bool
    reason: str
    prompt_tokens: int
    tokenizer_digest: str
    serving_digest: str
    feedback_digest: str
    digest: str
    stored_prose: int = 0

    def card(self) -> dict[str, object]:
        return {
            "kind": "serving-token-synergy",
            "schema": SCHEMA,
            "packet": PACKET,
            "parent": PARENT,
            "hit": 1 if self.admitted else 0,
            "law": self.reason,
            "citation": "docs/lineage/serving_token_synergy.md",
            "stored_prose": 0,
            "request_id": self.request_id,
            "prompt_tokens": self.prompt_tokens,
            "tokenizer_digest": self.tokenizer_digest,
            "serving_digest": self.serving_digest,
            "feedback_digest": self.feedback_digest,
            "digest": self.digest,
        }


class ServingTokenSynergy:
    """Binds one tokenizer identity to one closed-loop controller.

    Admission records are an in-process fence. They are not a durable ledger
    and they do not authorize model execution.
    """

    def __init__(self, controller: ClosedLoopServingController, identity: TokenizerIdentity) -> None:
        if not isinstance(controller, ClosedLoopServingController):
            raise SynergyError("ClosedLoopServingController required")
        if not isinstance(identity, TokenizerIdentity):
            raise SynergyError("TokenizerIdentity required")
        self.controller = controller
        self.identity = identity
        self._admitted: dict[str, tuple[int, str]] = {}

    def admit(
        self,
        *,
        request_id: str,
        prompt_tokens: int,
        slo: SLOTarget,
        kv_capacity_bytes: int,
        kv_used_bytes: int,
        queue_pressure_pct: int,
        tokenizer_digest: str,
    ) -> JointReceipt:
        self._require_identity(tokenizer_digest)
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 256:
            raise SynergyError("request_id required")
        if type(prompt_tokens) is not int or prompt_tokens < 0:
            raise SynergyError("prompt_tokens required")
        if request_id in self._admitted:
            raise SynergyError("request already admitted")
        decision = self.controller.decide(
            prompt_tokens=prompt_tokens,
            slo=slo,
            kv_capacity_bytes=kv_capacity_bytes,
            kv_used_bytes=kv_used_bytes,
            queue_pressure_pct=queue_pressure_pct,
        )
        if not isinstance(decision, ControlDecision):
            raise SynergyError("control decision required")
        if not decision.resource_plan.admitted:
            return self._receipt(
                request_id=request_id,
                admitted=False,
                reason=decision.resource_plan.reason,
                prompt_tokens=prompt_tokens,
                serving_digest=decision.digest,
                feedback_digest=decision.feedback_digest,
            )
        receipt = self._receipt(
            request_id=request_id,
            admitted=True,
            reason="admitted",
            prompt_tokens=prompt_tokens,
            serving_digest=decision.digest,
            feedback_digest=decision.feedback_digest,
        )
        self._admitted[request_id] = (prompt_tokens, receipt.digest)
        return receipt

    def observe(
        self,
        telemetry: RequestTelemetry,
        *,
        kv_bytes_per_token: int,
        tokenizer_digest: str,
        admission_digest: str,
    ) -> JointReceipt:
        self._require_identity(tokenizer_digest)
        if not isinstance(telemetry, RequestTelemetry):
            raise SynergyError("RequestTelemetry required")
        _hex64(admission_digest, "admission digest")
        bound = self._admitted.get(telemetry.request_id)
        if bound is None:
            raise SynergyError("observe without admission")
        prompt_tokens, expected = bound
        if not hmac.compare_digest(expected, admission_digest):
            raise SynergyError("admission digest mismatch")
        if telemetry.prompt_tokens != prompt_tokens:
            raise SynergyError("observation prompt diverges from admission")
        feedback = self.controller.observe(telemetry, kv_bytes_per_token=kv_bytes_per_token)
        self._admitted.pop(telemetry.request_id, None)
        return self._receipt(
            request_id=telemetry.request_id,
            admitted=True,
            reason="observed",
            prompt_tokens=prompt_tokens,
            serving_digest=feedback.digest,
            feedback_digest=feedback.digest,
        )

    def bind_checkpoints(
        self,
        tokenizer_checkpoint: Mapping[str, object],
        feedback_checkpoint: Mapping[str, object],
    ) -> dict[str, object]:
        """Cross-check the two checkpoint laws before a restart can resume."""
        if not isinstance(tokenizer_checkpoint, Mapping) or not isinstance(feedback_checkpoint, Mapping):
            raise SynergyError("checkpoints must be mappings")
        if tokenizer_checkpoint.get("digest") != self.identity.digest:
            raise SynergyError("tokenizer checkpoint is not the bound identity")
        vocab = tokenizer_checkpoint.get("vocabulary")
        if not isinstance(vocab, (list, tuple)) or len(vocab) != self.identity.vocab_size:
            raise SynergyError("tokenizer checkpoint vocabulary diverges")
        if any(type(token) is not str for token in vocab):
            raise SynergyError("tokenizer checkpoint vocabulary diverges")
        if tokenizer_checkpoint.get("unknown_token_id") != self.identity.unk:
            raise SynergyError("tokenizer checkpoint unk diverges")
        restored = DeterministicRuntimeEstimator.from_checkpoint(feedback_checkpoint)
        if restored.limits.max_samples != self.controller.estimator.limits.max_samples:
            raise SynergyError("feedback checkpoint limits diverge")
        body = {
            "schema": SCHEMA,
            "tokenizer_digest": self.identity.digest,
            "feedback_digest": feedback_checkpoint["digest"],
            "vocab_size": self.identity.vocab_size,
            "samples": restored.receipt().samples,
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return {**body, "digest": digest, "stored_prose": 0, "merge_authority": 0, "parent": PARENT}

    def _require_identity(self, tokenizer_digest: str) -> None:
        digest = _hex64(tokenizer_digest, "tokenizer digest")
        if not hmac.compare_digest(digest, self.identity.digest):
            raise SynergyError("tokenizer identity drift")

    def _receipt(
        self,
        *,
        request_id: str,
        admitted: bool,
        reason: str,
        prompt_tokens: int,
        serving_digest: str,
        feedback_digest: str,
    ) -> JointReceipt:
        body = {
            "schema": SCHEMA,
            "request_id": request_id,
            "admitted": admitted,
            "reason": reason,
            "prompt_tokens": prompt_tokens,
            "tokenizer_digest": self.identity.digest,
            "serving_digest": serving_digest,
            "feedback_digest": feedback_digest,
            "vocab_size": self.identity.vocab_size,
            "unk": self.identity.unk,
        }
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return JointReceipt(
            request_id=request_id,
            admitted=admitted,
            reason=reason,
            prompt_tokens=prompt_tokens,
            tokenizer_digest=self.identity.digest,
            serving_digest=serving_digest,
            feedback_digest=feedback_digest,
            digest=digest,
        )


__all__ = [
    "JointReceipt",
    "PACKET",
    "ServingTokenSynergy",
    "SynergyError",
    "TokenizerIdentity",
]
