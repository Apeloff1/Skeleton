"""API server — the serving face of Genesis.

Boots the Genesis orchestrator lazily on first request (never at import,
so tests and tooling can import this module without paying boot cost), and
exposes the substrate through a small set of canonical endpoints.

The server is deliberately thin: every endpoint delegates to a Genesis
handle. Subsystem logic never lives here.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from fastapi import FastAPI, HTTPException
except ImportError:  # skeleton core stays framework-free
    FastAPI = None  # type: ignore[assignment,misc]
    HTTPException = None  # type: ignore[assignment,misc]

from skeleton.genesis import Genesis

_genesis: Optional[Genesis] = None


def get_genesis() -> Genesis:
    """Boot-or-return the single Genesis instance."""
    global _genesis
    if _genesis is None:
        _genesis = Genesis().boot()
    return _genesis


def reset_genesis() -> None:
    """Test hook: drop the cached instance so the next request re-boots."""
    global _genesis
    _genesis = None


def create_app(seed: Optional[int] = None) -> "FastAPI":
    if FastAPI is None:
        raise RuntimeError(
            "fastapi is required for skeleton.api.server; "
            "install it or use the kernel directly"
        )

    if seed is not None:
        global _genesis
        _genesis = Genesis(seed=seed).boot()

    app = FastAPI(title="Skeleton API", version="16.0.0")

    @app.get("/health")
    def health() -> Dict[str, Any]:
        g = get_genesis()
        report = g.health()
        if not report["healthy"]:
            raise HTTPException(status_code=503, detail=report)
        return report

    @app.get("/subsystems")
    def subsystems() -> Dict[str, Any]:
        g = get_genesis()
        return g.report.to_dict()

    @app.post("/memory/query")
    def memory_query(body: Dict[str, Any]) -> Dict[str, Any]:
        g = get_genesis()
        trinity = g.get("trinity")
        query = str(body.get("query", ""))
        top_k = int(body.get("top_k", 5))
        results = trinity.query(query, top_k=top_k)
        return {
            "query": query,
            "results": [
                {
                    "id": r.chunk.id,
                    "text": r.chunk.text,
                    "score": r.score,
                    "rank": r.rank,
                    "tier": r.chunk.source_tier,
                }
                for r in results
            ],
        }

    return app
