"""Charter-law FastAPI gate — runs AFTER HMAC seal, BEFORE route handlers.

Composes ``require_seal`` then ``Governance.decide``. Fail-closed → 403.
Does not fork seal verification (#16); does not rewrite Gate middleware (#34).
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException

from skeleton.api.hmac_seal import require_seal
from skeleton.kernel.governance import Decision, get_governance


def require_charter(domain: str, action: str, *, default_weight: int = 0):
    """Dependency factory: seal first, then charter decide for (domain, action)."""

    def _gate(
        attester: str = Depends(require_seal),
        x_gf_actor_weight: Optional[str] = Header(default=None, alias="x-gf-actor-weight"),
    ) -> str:
        weight = default_weight
        if x_gf_actor_weight is not None and str(x_gf_actor_weight).strip() != "":
            try:
                weight = int(x_gf_actor_weight)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={"error": "invalid_actor_weight", "value": x_gf_actor_weight},
                ) from None
        decision: Decision = get_governance().decide(domain, action, weight)
        if not decision.permitted:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "charter_denied",
                    "domain": domain,
                    "action": action,
                    "reason": decision.reason,
                    "cited_rule": decision.cited_rule,
                },
            )
        return attester

    return _gate
