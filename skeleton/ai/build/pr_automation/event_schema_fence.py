"""Fail closed when a workflow event schema digest drifts. Parent #80."""
from __future__ import annotations

import hashlib
import hmac
import json

_HEX = set("0123456789abcdef")


class EventFenceError(ValueError):
    pass


def _hex64(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise EventFenceError("invalid event schema digest")
    return value


class EventSchemaFence:
    def __init__(self, schema_digest: str) -> None:
        self.schema_digest = _hex64(schema_digest)
        self._seen: dict[str, str] = {}

    def admit(self, *, run_id: str, schema_digest: str) -> dict[str, object]:
        if not isinstance(run_id, str) or not run_id or len(run_id) > 128:
            raise EventFenceError("invalid run id")
        digest = _hex64(schema_digest)
        if not hmac.compare_digest(digest, self.schema_digest):
            raise EventFenceError("event schema digest drift")
        if run_id in self._seen:
            raise EventFenceError("run already admitted")
        body = {"schema": "skeleton.ai.event-schema-fence.v1", "run_id": run_id, "schema_digest": digest}
        receipt = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        self._seen[run_id] = receipt
        return {**body, "digest": receipt, "stored_prose": 0, "parent": "#80", "hit": 1}


__all__ = ["EventFenceError", "EventSchemaFence"]
