"""Pin tokenizer identity on admission checkpoint restore. Parent #80. stored_prose=0."""
from __future__ import annotations

import hashlib
import hmac
import json
from typing import Mapping

from .admission_checkpoint import restore_admission_scheduler
from .admission_scheduler import RuntimeAdmissionScheduler
from .flgb_model_runtime import ModelRuntimeError

_HEX = set("0123456789abcdef")


class RestoreBindError(ModelRuntimeError):
    """Fail-closed when restore is not pinned to the tokenizer identity."""


def _hex64(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise RestoreBindError("invalid tokenizer digest")
    return value


def restore_bound(
    snapshot: Mapping[str, object],
    *,
    tokenizer_digest: str,
    expected_digest: str | None = None,
) -> dict[str, object]:
    digest = _hex64(tokenizer_digest)
    if not isinstance(snapshot, Mapping):
        raise RestoreBindError("snapshot required")
    scheduler = restore_admission_scheduler(snapshot, expected_digest=expected_digest)
    if not isinstance(scheduler, RuntimeAdmissionScheduler):
        raise RestoreBindError("scheduler required")
    body = {
        "schema": "skeleton.ai.restore-token-bind.v1",
        "tokenizer_digest": digest,
        "scheduler_digest": snapshot.get("digest"),
        "sequence": snapshot.get("sequence"),
    }
    receipt = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        **body,
        "digest": receipt,
        "stored_prose": 0,
        "parent": "#80",
        "merge_authority": 0,
        "scheduler": scheduler,
    }


def same_identity(left: str, right: str) -> None:
    if not hmac.compare_digest(_hex64(left), _hex64(right)):
        raise RestoreBindError("tokenizer identity drift")


__all__ = ["RestoreBindError", "restore_bound", "same_identity"]
