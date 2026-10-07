"""
dna_preview_router
==================

Multi-domain ``POST /api/dna/preview/{domain}`` endpoints. Lets the
frontend cockpits (Builder / Jeeves / Academy) show users the exact
prompt directive block the LLM would receive without burning a real
generation.

Shared hardening:
    • Typed Pydantic body (malformed JSON → 422).
    • Domain-scoped per-IP rate limit (30 calls / 60 s).
    • Reuses the hardened ``dna_translator_core`` sanitiser + translator.
    • Unknown domain → 404 (no information leak about which domains exist
      beyond the registry).
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .dna_translator_core import (
    sanitise, translate, stats as core_stats, limits as core_limits,
    get_domain,
)
# Importing this module registers all domains.
from . import dna_domains  # noqa: F401

router = APIRouter(prefix="/dna", tags=["DNA Preview"])

_PREVIEW_WINDOW_S: float = 60.0
_PREVIEW_MAX_PER_WINDOW: int = 30
# Keyed by ``(client_ip, domain)`` so domains have independent budgets.
_preview_counters: Dict[str, List[float]] = {}


def _rate_limit_key(ip: str, domain: str) -> str:
    return f"{ip}::{domain}"


def _rate_limit(ip: str, domain: str) -> bool:
    now = time.time()
    bucket = _preview_counters.setdefault(_rate_limit_key(ip, domain), [])
    bucket[:] = [t for t in bucket if now - t < _PREVIEW_WINDOW_S]
    if len(bucket) >= _PREVIEW_MAX_PER_WINDOW:
        return False
    bucket.append(now)
    return True


class DnaPreviewBody(BaseModel):
    """Generic DNA payload — accepted by every domain endpoint.

    The frontend always posts as ``{ "builder_dna": { … } }`` for
    consistency, regardless of the actual domain. The translator only
    looks at keys with the domain's prefix, so foreign keys are dropped
    by ``sanitise``.
    """
    builder_dna: Optional[Dict[str, float]] = Field(
        None,
        description="Cockpit map. Keys are sanitised against the domain prefix.",
    )


@router.post("/preview/{domain}")
async def preview(domain: str, body: DnaPreviewBody, request: Request) -> Dict[str, Any]:
    """Return prompt directives + stats + limits for ``domain``."""
    cfg = get_domain(domain)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Unknown DNA domain: {domain!r}")
    ip = (request.client.host if request.client else "unknown") or "unknown"
    if not _rate_limit(ip, domain):
        raise HTTPException(
            status_code=429,
            detail=f"Too many preview calls. Cool off for {int(_PREVIEW_WINDOW_S)}s.",
        )
    return {
        "domain": domain,
        "stats": core_stats(body.builder_dna, cfg),
        "directives": translate(body.builder_dna, cfg),
        "limits": core_limits(),
    }


@router.get("/domains")
async def list_domains() -> Dict[str, Any]:
    """Tiny discovery endpoint — lists available preview domains.

    Surfaces the key prefix + group order so a future frontend can
    auto-render unknown domains without hard-coding.
    """
    from .dna_domains import DOMAINS
    return {
        "domains": [
            {
                "name": d.name,
                "key_prefix": d.key_prefix,
                "group_order": list(d.group_order),
                "blurb": d.blurb,
            }
            for d in DOMAINS.values()
        ],
        "limits": core_limits(),
    }
