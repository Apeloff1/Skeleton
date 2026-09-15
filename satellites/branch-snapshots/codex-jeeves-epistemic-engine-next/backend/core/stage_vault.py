"""
🧠 STAGE VAULT — wires the hyperscale knowledge vault (game_knowledge_engine) into EVERY
Snowball stage so each stage can load domain expertise for manual passes + auto-improve.

vault_for_stage(stage) returns the most relevant knowledge domains + concrete core-knowledge
tips for that pipeline stage, drawn from the 50 KNOWLEDGE_DOMAINS.
"""
from __future__ import annotations

from routes.game_knowledge_engine import KNOWLEDGE_DOMAINS

# Each stage → category buckets + keyword hints used to rank the 50 domains.
_STAGE_PROFILE = {
    "spec":       (["game_design", "meta", "business"], ["mechanic", "design", "vision", "scope", "player"]),
    "world":      (["game_design", "art", "narrative"], ["world", "level", "environment", "lore", "biome", "lighting"]),
    "narrative":  (["narrative", "game_design", "meta"], ["narrative", "story", "dialogue", "character", "quest", "writing"]),
    "mechanics":  (["game_design", "engineering"], ["mechanic", "balance", "economy", "physics", "system", "combat"]),
    "procedural": (["engineering", "art"], ["procedural", "generation", "algorithm", "math", "noise", "graphics"]),
    "assets":     (["art"], ["art", "asset", "sprite", "model", "texture", "render", "animation", "audio"]),
    "qa":         (["meta", "engineering"], ["qa", "test", "quality", "bug", "playtest", "analytics"]),
    "build":      (["engineering", "meta"], ["build", "engine", "performance", "optimization", "deploy", "pipeline"]),
    "launch":     (["business", "meta"], ["launch", "marketing", "monetization", "community", "live", "publish"]),
    # ── Extended game-build features (game-mount: vault connected to every step) ──
    "systems":    (["game_design", "engineering"], ["system", "mechanic", "rule", "state", "loop", "progression"]),
    "vfx":        (["art", "engineering"], ["vfx", "shader", "particle", "material", "lighting", "render", "effect"]),
    "audio":      (["art"], ["audio", "sound", "music", "sfx", "mix", "score", "ambience"]),
    "ui":         (["art", "game_design"], ["ui", "ux", "hud", "menu", "interface", "accessibility", "layout"]),
    "multiplayer":(["engineering"], ["multiplayer", "netcode", "server", "sync", "latency", "matchmaking", "rollback"]),
    "balance":    (["game_design", "engineering"], ["balance", "economy", "tuning", "difficulty", "reward", "curve"]),
    "monetization":(["business", "meta"], ["monetization", "iap", "ads", "pricing", "ltv", "retention", "store"]),
    "narrative_vo":(["narrative", "art"], ["voice", "dialogue", "narration", "cadence", "delivery", "tone"]),
}


def _score(domain: dict, cats: list[str], kws: list[str]) -> float:
    s = 0.0
    if domain.get("category") in cats:
        s += 1.0
    blob = (domain.get("name", "") + " " + domain.get("id", "") + " "
            + " ".join(domain.get("core_knowledge", []))).lower()
    s += 0.25 * sum(1 for k in kws if k in blob)
    if domain.get("depth") == "Oracle":
        s += 0.15
    return s


def vault_for_stage(stage: str, max_domains: int = 4, tips_per: int = 4) -> dict:
    cats, kws = _STAGE_PROFILE.get(stage, (["meta"], []))
    ranked = sorted(KNOWLEDGE_DOMAINS, key=lambda d: _score(d, cats, kws), reverse=True)
    picked = [d for d in ranked if _score(d, cats, kws) > 0][:max_domains] or ranked[:max_domains]
    domains, tips = [], []
    for d in picked:
        ck = (d.get("core_knowledge") or [])[:tips_per]
        domains.append({"id": d.get("id"), "name": d.get("name"),
                        "category": d.get("category"), "depth": d.get("depth"),
                        "practitioners": (d.get("legendary_practitioners") or [])[:4],
                        "cutting_edge": (d.get("cutting_edge") or [])[:2]})
        tips.extend(ck)
    return {"stage": stage, "domain_count": len(domains), "domains": domains, "tips": tips[:12]}


def vault_brief(stage: str) -> str:
    """A compact text brief injected into the agent transcript / generation context."""
    v = vault_for_stage(stage)
    names = ", ".join(d["name"] for d in v["domains"])
    tips = "; ".join(v["tips"][:5])
    return f"Vault loaded ({names}). Apply: {tips}"
