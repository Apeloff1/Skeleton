"""Refuse a redundant publish under a foreign tokenizer digest. Parent #80."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Sequence

from .admission_redundancy import CheckpointReplica, publish_redundant_checkpoint
from .admission_scheduler import RuntimeAdmissionScheduler
from .flgb_model_runtime import ModelRuntimeError

_HEX = set("0123456789abcdef")


class ReplicaPinError(ModelRuntimeError):
    pass


def _hex64(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise ReplicaPinError("invalid tokenizer digest")
    return value


def publish_pinned(
    scheduler: RuntimeAdmissionScheduler,
    replicas: Sequence[CheckpointReplica],
    *,
    tokenizer_digest: str,
    bound_digest: str,
) -> dict[str, object]:
    presented = _hex64(tokenizer_digest)
    bound = _hex64(bound_digest)
    if not hmac.compare_digest(presented, bound):
        raise ReplicaPinError("tokenizer identity drift")
    receipt = publish_redundant_checkpoint(scheduler, replicas)
    body = {
        "schema": "skeleton.ai.replica-token-pin.v1",
        "tokenizer_digest": bound,
        "replication_digest": receipt.digest,
        "sequence": receipt.sequence,
    }
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {**body, "digest": digest, "stored_prose": 0, "parent": "#80", "merge_authority": 0, "receipt": receipt}


__all__ = ["ReplicaPinError", "publish_pinned"]
