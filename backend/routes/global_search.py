"""
routes/global_search.py — App-wide quick-search aggregator (2026-06-18)

GET /api/search/global?q=...  → categorized results across the whole app:
  • Features / screens  (curated registry with deep-link routes)
  • Capability systems   (the 40 generated capabilities)
  • Agent datasets       (the 16 local knowledge packs)
  • Game-dev pipeline     (the 8 production stages)

Powers the floating "⌘K"-style global search overlay so users can jump
anywhere from one place.
"""
from __future__ import annotations
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/search", tags=["global-search"])

# ── Curated feature registry: every major screen + how to reach it ──────────
# (label, route, category, keywords)
APP_FEATURES = [
    ("Home / Hub", "/", "Navigation", ["home", "hub", "dashboard", "start"]),
    ("All Features", "/menu", "Navigation", ["menu", "features", "all", "browse"]),
    ("Settings", "/settings", "Settings", ["settings", "preferences", "config"]),
    ("Feature Flags", "/feature-flags", "Settings", ["flags", "toggles", "experiments"]),
    ("Build Vault", "/settings", "Settings", ["vault", "disk", "storage", "compression", "reclaim", "export", "zip"]),
    ("Audit Routes", "/audit-routes", "Diagnostics", ["audit", "routes", "endpoints", "debug"]),
    ("Agent Once-Over", "/agent-review", "Diagnostics", ["agents", "review", "health", "cadence", "once-over"]),
    ("Capability Systems", "/capabilities", "Galaxy Studio", ["capabilities", "systems", "engines", "physics", "netcode", "ai"]),
    ("Galaxy Studio", "/galaxy", "Galaxy Studio", ["galaxy", "game", "builder", "studio", "factory", "create game"]),
    ("My Builds", "/my-builds", "Galaxy Studio", ["builds", "games", "projects", "my builds"]),
    ("Curriculum", "/curriculum", "Learn", ["curriculum", "classes", "courses", "syllabus", "learn"]),
    ("Reading Library", "/reading", "Learn", ["reading", "library", "books", "tracks"]),
    ("Notes", "/notes", "Productivity", ["notes", "notebook", "memo", "write"]),
    ("Code Playground", "/code-playground", "Code", ["code", "playground", "editor", "run", "sandbox"]),
    ("Tools Arena", "/tools-arena", "Tools", ["tools", "arena", "utilities", "jeeves", "search"]),
    ("Leaderboards", "/leaderboards", "Gamification", ["leaderboard", "ranking", "scores", "top"]),
    ("Daily Challenge", "/daily", "Gamification", ["daily", "challenge", "streak"]),
    ("Knowledge Databases", "/knowledge-databases", "Learn", ["knowledge", "database", "facts", "reference"]),
    ("Jeeves", "/jeeves", "AI", ["jeeves", "assistant", "ai", "chat", "help"]),
]


def _score(q: str, label: str, keywords) -> int:
    """Cheap relevance score: exact > prefix > substring on label/keywords."""
    ql = q.lower().strip()
    if not ql:
        return 0
    ll = label.lower()
    if ll == ql:
        return 100
    if ll.startswith(ql):
        return 80
    if ql in ll:
        return 60
    for kw in keywords:
        k = kw.lower()
        if k == ql:
            return 55
        if k.startswith(ql):
            return 45
        if ql in k:
            return 30
    return 0


@router.get("/global")
async def global_search(q: str = Query("", max_length=64), limit: int = 8):
    """Aggregated quick-search across features + Galaxy Studio systems."""
    ql = q.strip()
    results = {"features": [], "capabilities": [], "datasets": [], "pipeline": []}
    if not ql:
        return {"ok": True, "query": q, "total": 0, "results": results}

    # 1) Features / screens
    feats = []
    for label, route, cat, kws in APP_FEATURES:
        s = _score(ql, label, kws)
        if s > 0:
            feats.append({"label": label, "route": route, "category": cat, "score": s})
    feats.sort(key=lambda r: r["score"], reverse=True)
    results["features"] = feats[:limit]

    # 2) Capability systems
    try:
        from routes import galaxy_studio_capabilities as _caps
        for spec in _caps.CAPABILITY_SPECS:
            s = _score(ql, spec["title"], [spec["id"]] + spec["subsystems"])
            if s > 0:
                results["capabilities"].append(
                    {"label": spec["title"], "route": "/capabilities", "category": spec["category"], "score": s})
        results["capabilities"].sort(key=lambda r: r["score"], reverse=True)
        results["capabilities"] = results["capabilities"][:limit]
    except Exception:
        pass

    # 3) Agent datasets
    try:
        from routes import galaxy_studio_datasets as _ds
        for d in _ds.DATASETS:
            s = _score(ql, d["title"], [d["id"], d["kind"]])
            if s > 0:
                results["datasets"].append(
                    {"label": d["title"], "route": "/capabilities", "category": "Dataset", "score": s})
        results["datasets"].sort(key=lambda r: r["score"], reverse=True)
        results["datasets"] = results["datasets"][:limit]
    except Exception:
        pass

    # 4) Pipeline stages
    try:
        from routes import galaxy_studio_gamedev_pipeline as _gdp
        for st in _gdp.PIPELINE_STAGES:
            s = _score(ql, st["title"], [st["id"]] + st["tasks"])
            if s > 0:
                results["pipeline"].append(
                    {"label": st["title"], "route": "/capabilities", "category": "Pipeline", "score": s})
        results["pipeline"].sort(key=lambda r: r["score"], reverse=True)
        results["pipeline"] = results["pipeline"][:limit]
    except Exception:
        pass

    total = sum(len(v) for v in results.values())
    return {"ok": True, "query": q, "total": total, "results": results}
