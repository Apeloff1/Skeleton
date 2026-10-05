"""
services/memory_engine.py — unified memory stack orchestrator (facade).

Layers, cheapest-first (the order a request should consult memory):

  1. MAG fillers  — persistent preemptive token blocks, always cache-hot.
                    Answers "what context should already be in the window?"
  2. CAG prefix   — deterministic rendered prefix; provider KV-cache reuses
                    it at ~10% billing when the sha matches the last call.
  3. RAG retrieval — ChromaDB semantic search over sessions/concepts/context;
                    only the dynamic tail. Short, per-request, full rate.

The orchestrator composes the final prompt and reports a cost ledger so
callers (and dashboards) can see exactly how many tokens were billed at
cached vs full rate.

Facade note (B4c, 2026-08-28): this module is now a thin facade. Everything
it touches — compose_prompt / jeeves_system_prefix (services.cag) and
get_store / get_warmer (services.mag) — resolves through guarded shims to
the canonical ``skeleton.memory.prefix_renderer`` and
``skeleton.memory.warmer`` implementations whenever the skeleton package is
importable, with byte-identical local fallbacks otherwise. No logic lives
here beyond prompt assembly and the cost ledger.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from services.cag import CAGPrefix, compose_prompt, jeeves_system_prefix
from services.mag import get_store, get_warmer

# RAG is optional at runtime (ChromaDB may be absent on minimal deploys).
try:
    from services.rag_service import RAGService
    _rag: RAGService | None = RAGService()
except Exception:
    _rag = None


@dataclass
class MemoryContext:
    """Everything assembled for one LLM call."""
    prompt: str
    prefix_sha: str
    cached_tokens: int
    fresh_tokens: int
    total_tokens: int
    retrieved_count: int
    fillers_used: list[str]
    rag_available: bool
    cost: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prefix_sha": self.prefix_sha,
            "cached_tokens": self.cached_tokens,
            "fresh_tokens": self.fresh_tokens,
            "total_tokens": self.total_tokens,
            "retrieved_count": self.retrieved_count,
            "fillers_used": self.fillers_used,
            "rag_available": self.rag_available,
            "cost": self.cost,
        }


# Cached-rate discount for provider prompt caching (OpenAI/Anthropic ~90% off).
CACHED_RATE = 0.10
# Conservative blended price per 1M input tokens for ledger estimates.
PRICE_PER_MTOK = float(__import__("os").environ.get("MEMORY_PRICE_PER_MTOK", "2.50"))


def _cost_ledger(cached_tokens: int, fresh_tokens: int) -> dict:
    full_price = (cached_tokens + fresh_tokens) / 1_000_000 * PRICE_PER_MTOK
    actual = (cached_tokens * CACHED_RATE + fresh_tokens) / 1_000_000 * PRICE_PER_MTOK
    return {
        "cached_tokens": cached_tokens,
        "fresh_tokens": fresh_tokens,
        "cached_rate": CACHED_RATE,
        "est_full_price_usd": round(full_price, 6),
        "est_actual_usd": round(actual, 6),
        "est_savings_usd": round(full_price - actual, 6),
        "savings_pct": round(100 * (1 - actual / full_price), 1) if full_price else 0.0,
    }


class MemoryEngine:
    """Facade over MAG + CAG + RAG."""

    def __init__(self) -> None:
        self.requests = 0
        self.total_cached = 0
        self.total_fresh = 0

    def build_context(
        self,
        user_query: str,
        *,
        user_id: str | None = None,
        pipeline: str | None = None,
        retrieve_k: int = 3,
        prefix: CAGPrefix | None = None,
    ) -> MemoryContext:
        """Assemble the full prompt for one tutoring/co-coding call."""
        self.requests += 1

        prefix = prefix or jeeves_system_prefix()

        retrieved: list[str] = []
        if _rag is not None and user_id:
            try:
                hits = _rag.get_relevant_context(user_id, user_query, pipeline=pipeline, limit=retrieve_k)
                retrieved = [h["content"] for h in hits]
            except Exception:
                retrieved = []

        prompt, meta = compose_prompt(prefix, user_query, retrieved)

        cached = meta["cached_tokens"]
        fresh = meta["fresh_tokens"]
        self.total_cached += cached
        self.total_fresh += fresh

        return MemoryContext(
            prompt=prompt,
            prefix_sha=meta["prefix_sha"],
            cached_tokens=cached,
            fresh_tokens=fresh,
            total_tokens=meta["total_tokens"],
            retrieved_count=len(retrieved),
            fillers_used=[f.key for f in get_store().all() if f.is_fresh()],
            rag_available=_rag is not None,
            cost=_cost_ledger(cached, fresh),
        )

    def health(self) -> dict:
        store_stats = get_store().stats()
        warmer_stats = get_warmer().stats()
        from services.cag import registry as _reg
        return {
            "rag_available": _rag is not None,
            "cag": _reg.stats(),
            "mag": {"store": store_stats, "warmer": warmer_stats},
            "requests": self.requests,
            "lifetime_cached_tokens": self.total_cached,
            "lifetime_fresh_tokens": self.total_fresh,
            "lifetime_est_savings_usd": round(
                (self.total_cached * (1 - CACHED_RATE)) / 1_000_000 * PRICE_PER_MTOK, 4
            ),
        }


_engine: MemoryEngine | None = None


def get_memory_engine() -> MemoryEngine:
    global _engine
    if _engine is None:
        _engine = MemoryEngine()
    return _engine


def boot() -> None:
    """Server-startup hook: prime MAG (which registers fillers, reloads the
    disk store into CAG, and starts the preemptive warmer)."""
    try:
        from services.mag import prime
        prime()
    except Exception:
        pass  # memory is an optimization; never block boot
