"""Bind tokenizer identity into a serving plan receipt. Parent #80. stored_prose=0."""
from __future__ import annotations

import hashlib
import hmac
import json

from .slo_planner import ResourcePlan, SLOResourcePlanner

_HEX = set("0123456789abcdef")


class PlanBindError(ValueError):
    """Fail-closed when a plan is asked to ride a foreign tokenizer digest."""


def _hex64(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(ch not in _HEX for ch in value):
        raise PlanBindError("invalid tokenizer digest")
    return value


class PlanIdentity:
    def __init__(self, planner: SLOResourcePlanner, tokenizer_digest: str) -> None:
        if not isinstance(planner, SLOResourcePlanner):
            raise PlanBindError("SLOResourcePlanner required")
        self.planner = planner
        self.tokenizer_digest = _hex64(tokenizer_digest)

    def plan(self, *, tokenizer_digest: str, **kwargs: object) -> dict[str, object]:
        digest = _hex64(tokenizer_digest)
        if not hmac.compare_digest(digest, self.tokenizer_digest):
            raise PlanBindError("tokenizer identity drift")
        resource = self.planner.plan(**kwargs)
        if not isinstance(resource, ResourcePlan):
            raise PlanBindError("ResourcePlan required")
        body = {
            "schema": "skeleton.ai.plan-token-bind.v1",
            "tokenizer_digest": digest,
            "plan_digest": resource.digest,
            "admitted": resource.admitted,
            "reason": resource.reason,
            "prompt_tokens": kwargs.get("prompt_tokens"),
            "queue_pressure_pct": kwargs.get("queue_pressure_pct"),
        }
        receipt = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        return {
            **body,
            "digest": receipt,
            "stored_prose": 0,
            "parent": "#80",
            "merge_authority": 0,
            "plan": resource,
        }


__all__ = ["PlanBindError", "PlanIdentity"]
