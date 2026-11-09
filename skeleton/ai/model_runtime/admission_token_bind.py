"""Bind a tokenizer digest to draft admission submits. Parent #80. stored_prose=0."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json

from .admission_scheduler import RuntimeAdmissionScheduler
from .flgb_model_runtime import BatchRequest, ModelRuntimeError

_HEX = set("0123456789abcdef")


class AdmissionBindError(ModelRuntimeError):
    """Fail-closed when a submit is not the bound tokenizer identity."""


def _hex64(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise AdmissionBindError("invalid tokenizer digest")
    return value


@dataclass(frozen=True, slots=True)
class BoundSubmit:
    request_id: str
    tokenizer_digest: str
    digest: str

    def card(self) -> dict[str, object]:
        return {
            "kind": "admission-token-bind",
            "parent": "#80",
            "stored_prose": 0,
            "hit": 1,
            "law": "bound",
            "request_id": self.request_id,
            "tokenizer_digest": self.tokenizer_digest,
            "digest": self.digest,
        }


class AdmissionIdentityGate:
    """Stamps one tokenizer identity onto scheduler submits. Does not admit by itself."""

    def __init__(self, scheduler: RuntimeAdmissionScheduler, tokenizer_digest: str) -> None:
        if not isinstance(scheduler, RuntimeAdmissionScheduler):
            raise AdmissionBindError("RuntimeAdmissionScheduler required")
        self.scheduler = scheduler
        self.tokenizer_digest = _hex64(tokenizer_digest)
        self._bound: dict[str, str] = {}

    def submit(self, request: BatchRequest, *, kv_bytes: int, tokenizer_digest: str, pinned_kv: bool = False) -> BoundSubmit:
        digest = _hex64(tokenizer_digest)
        if not hmac.compare_digest(digest, self.tokenizer_digest):
            raise AdmissionBindError("tokenizer identity drift")
        if not isinstance(request, BatchRequest):
            raise AdmissionBindError("BatchRequest required")
        if request.request_id in self._bound:
            raise AdmissionBindError("request already bound")
        self.scheduler.submit(request, kv_bytes=kv_bytes, pinned_kv=pinned_kv)
        body = {
            "request_id": request.request_id,
            "tokenizer_digest": digest,
            "prompt_tokens": request.prompt_tokens,
            "kv_bytes": kv_bytes,
        }
        receipt = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        self._bound[request.request_id] = receipt
        return BoundSubmit(request.request_id, digest, receipt)

    def require(self, request_id: str, receipt: str) -> None:
        expected = self._bound.get(request_id)
        if expected is None or not hmac.compare_digest(expected, receipt):
            raise AdmissionBindError("unbound admission")


__all__ = ["AdmissionBindError", "AdmissionIdentityGate", "BoundSubmit"]
