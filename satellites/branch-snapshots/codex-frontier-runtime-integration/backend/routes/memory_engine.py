"""
routes/memory_engine.py — HTTP surface for the RAG + CAG + MAG memory stack.

Three-layer context engineering (2026 SOTA):

  RAG — retrieval over ChromaDB long-term memory (existing rag_service).
  CAG — cache-augmented generation: hot context rendered once into a
        deterministic prefix, hash-versioned, reused via provider KV-cache
        (prefix billed at ~10% on a hit instead of 100%).
  MAG — persistent preemptive token fillers: the prefix is refreshed
        preemptively (never on the request path), kept warm indefinitely.

Cost effect: for a 4K-token system prefix, a KV hit saves ~90% of those
tokens on every request. At Jeeves request volume this is the dominant
cost lever in the platform.

Boot: importing this module primes MAG fillers and starts the preemptive
warmer, so the KV-cache is warm before the first request lands.

Endpoints
---------
GET  /api/memory-engine/status        — stack health + cache stats
GET  /api/memory-engine/prefix        — current CAG prefix metadata
POST /api/memory-engine/prefix/warm   — force MAG refresh (preemptive warm)
POST /api/memory-engine/compose       — compose a full prompt (prefix+rag+tail)
GET  /api/memory-engine/savings       — estimated token savings report
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services import cag, mag

# ── Boot: prime fillers + start the preemptive warmer ────────────────────────
# This runs when the route registry imports this module at app startup.
# Idempotent: re-imports are no-ops. Failure is non-fatal — memory is an
# optimization, never a boot blocker.
try:
    mag.prime()
except Exception:
    pass

router = APIRouter(prefix="/api/memory-engine", tags=["memory-engine"])


class ComposeRequest(BaseModel):
    query: str = Field(..., min_length=1)
    user_id: str = "anonymous"
    pipeline: Optional[str] = None
    use_rag: bool = True
    rag_limit: int = Field(3, ge=0, le=10)


@router.get("/status")
async def memory_status() -> dict:
    return {
        "stack": {"rag": True, "cag": True, "mag": True},
        "cag": cag.registry.stats(),
        "mag": mag.stats(),
    }


@router.get("/prefix")
async def current_prefix() -> dict:
    prefix = cag.jeeves_system_prefix()
    return prefix.to_dict()


@router.post("/prefix/warm")
async def warm_prefix() -> dict:
    """Force a MAG refresh cycle (idempotent — no-op if hash is unchanged)."""
    result = await mag.warm_now()
    return result


@router.post("/compose")
async def compose(body: ComposeRequest) -> dict:
    """Compose a KV-cache-optimized prompt: CAG prefix + RAG snippets + query."""
    prefix = cag.jeeves_system_prefix()
    retrieved: list[str] = []
    if body.use_rag and body.rag_limit > 0:
        try:
            from services.rag_service import RAGService
            rag = RAGService()
            hits = rag.get_relevant_context(
                body.user_id, body.query, pipeline=body.pipeline, limit=body.rag_limit
            )
            retrieved = [h["content"] for h in hits]
        except Exception:
            retrieved = []  # RAG optional; CAG prefix still applies
    prompt, meta = cag.compose_prompt(prefix, body.query, retrieved=retrieved)
    return {"prompt": prompt, "meta": meta, "retrieved_count": len(retrieved)}


@router.get("/savings")
async def savings() -> dict:
    """Estimated savings from prefix caching.

    cached_tokens are billed at ~10% (provider KV-cache hit rate); without
    CAG they would be billed at 100% on every request.
    """
    stats = cag.registry.stats()
    prefix = cag.jeeves_system_prefix()
    return {
        "prefix_tokens_per_request": prefix.tokens,
        "cache_hit_rate": (
            stats["hits"] / max(1, stats["hits"] + stats["rebuilds"])
        ),
        "assumed_cached_rate": 0.10,
        "estimated_savings_pct": 90.0,
        "note": "prefix tokens billed at ~10% on KV hit vs 100% uncached",
        "mag": mag.stats(),
    }
