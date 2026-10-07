"""
╔════════════════════════════════════════════════════════════════════════╗
║  VAULT GDD + MOUNT — fold the forged gamefiles into a living document.   ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Reads the Item-Foundry gamefiles that live in the Vault (galaxy_vault   ║
║  / galaxy_build_items) for a build and:                                  ║
║                                                                        ║
║    • compiles a vault-grounded Game Design Document (GDD) — overview,    ║
║      per-stage knowledge grounding, an artifact/loot table, a palette    ║
║      board and a placement map — straight from the gamefiles.            ║
║    • MOUNTS the build: persists a mount manifest (GDD + coverage + item  ║
║      stats) into galaxy_vault_mounts so the build is wired into the      ║
║      snowball flow.                                                      ║
║                                                                        ║
║  Fully deterministic (pure string build from DB rows) with an optional   ║
║  LLM polish hook that only ever ENRICHES — never blocks — the document.  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import time
from typing import Any

from core import item_foundry as foundry

# Stages that bear items, mirrors foundry.ITEM_STAGES with display metadata.
_STAGE_META: dict[str, tuple[str, str]] = {
    "world": ("🌍", "World & Landmarks"),
    "narrative": ("📖", "Narrative & Lore"),
    "mechanics": ("⚙️", "Mechanics & Systems"),
    "procedural": ("🧬", "Procedural Content"),
    "tileset": ("🧱", "Tilesets & Environment"),
    "assets": ("🎨", "Assets & Visuals"),
}


def read_gamefiles(build_id: str) -> dict:
    """Pull the build record + forged gamefiles (items) from the Vault."""
    items: list[dict] = foundry.list_items(build_id)
    build: dict = {}
    manifest: dict = {}
    try:
        from core.databases import get_sync_db
        db = get_sync_db()
        build = db["galaxy_builds"].find_one({"build_id": build_id}, {"_id": 0}) or {}
        manifest = db["galaxy_item_manifests"].find_one(
            {"build_id": build_id}, {"_id": 0}) or {}
    except Exception:
        pass
    return {"build": build, "items": items, "manifest": manifest}


def foundry_stats(items: list[dict]) -> dict:
    """Aggregate gamefile stats: grade histogram, archetype + palette usage,
    fidelity, per-stage counts and the busiest forging agents."""
    grade_hist: dict[int, int] = {}
    archetypes: dict[str, int] = {}
    palettes: dict[str, int] = {}
    by_stage: dict[str, int] = {}
    agents: dict[str, int] = {}
    fids: list[float] = []
    for it in items:
        g = int(it.get("grade", 0))
        grade_hist[g] = grade_hist.get(g, 0) + 1
        arch = (it.get("definition") or {}).get("archetype") or "Artifact"
        archetypes[arch] = archetypes.get(arch, 0) + 1
        skin = it.get("skin") or {}
        pal = skin.get("palette_name") or "—"
        palettes[pal] = palettes.get(pal, 0) + 1
        by_stage[it.get("stage", "—")] = by_stage.get(it.get("stage", "—"), 0) + 1
        code = it.get("agent_code") or "—"
        agents[code] = agents.get(code, 0) + 1
        if isinstance(skin.get("fidelity"), (int, float)):
            fids.append(float(skin["fidelity"]))
    top_agents = sorted(agents.items(), key=lambda kv: -kv[1])[:8]
    top_arch = sorted(archetypes.items(), key=lambda kv: -kv[1])[:8]
    return {
        "total_items": len(items),
        "grade_histogram": [{"grade": g, "count": grade_hist[g]} for g in sorted(grade_hist)],
        "archetypes": [{"name": k, "count": v} for k, v in top_arch],
        "distinct_archetypes": len(archetypes),
        "palettes": [{"name": k, "count": v} for k, v in
                     sorted(palettes.items(), key=lambda kv: -kv[1])],
        "by_stage": [{"stage": k, "count": by_stage[k]} for k in
                     sorted(by_stage, key=lambda s: list(_STAGE_META).index(s)
                            if s in _STAGE_META else 99)],
        "avg_fidelity": round(sum(fids) / len(fids), 3) if fids else 0.0,
        "avg_grade": round(sum(g * c for g, c in grade_hist.items())
                           / max(1, len(items)), 2),
        "top_agents": [{"code": c, "items": n} for c, n in top_agents],
    }


def _loot_table(items: list[dict]) -> str:
    """Markdown table of every gamefile/item, grouped by stage."""
    rows: list[str] = []
    by_stage: dict[str, list[dict]] = {}
    for it in items:
        by_stage.setdefault(it.get("stage", "—"), []).append(it)
    for stage in foundry.ITEM_STAGES:
        bucket = by_stage.get(stage)
        if not bucket:
            continue
        icon, label = _STAGE_META.get(stage, ("•", stage.title()))
        rows.append(f"### {icon} {label}")
        rows.append("")
        rows.append("| Item | Tier | Grade | Archetype | Region | Spawn | By |")
        rows.append("|------|------|-------|-----------|--------|-------|----|")
        for it in sorted(bucket, key=lambda x: -int(x.get("grade", 0))):
            d = it.get("definition") or {}
            pl = it.get("placement") or {}
            rows.append(
                f"| {it.get('name', '—')} | {d.get('tier', '—')} | "
                f"{it.get('grade', '—')} | {d.get('archetype', '—')} | "
                f"{pl.get('region', '—')} | {pl.get('spawn_rule', '—')} | "
                f"{it.get('agent_code', '—')} |"
            )
        rows.append("")
    return "\n".join(rows)


def compile_gdd(build: dict, items: list[dict], manifest: dict) -> str:
    """Compile a vault-grounded GDD straight from the gamefiles."""
    title = build.get("title") or build.get("name") or "Untitled Build"
    genre = (build.get("genre") or manifest.get("genre") or "rpg")
    stats = foundry_stats(items)
    L: list[str] = [
        f"# 🎮 Game Design Document — {title}",
        "",
        f"**Genre:** {genre}  ·  **Build:** `{build.get('build_id', '—')}`",
        f"**Forged gamefiles:** {stats['total_items']}  ·  "
        f"**Avg grade:** {stats['avg_grade']}  ·  "
        f"**Avg fidelity:** {stats['avg_fidelity']}  ·  "
        f"**Archetypes:** {stats['distinct_archetypes']}",
        "",
        "> This document is compiled **directly from the Vault gamefiles** the agent "
        "platoons forged — every item below is folded into the game and graded above "
        "the base gamefiles.",
        "",
        "## 1. Overview",
        "",
        f"_{title}_ is a {genre} experience assembled by the agent swarm. Each agent in "
        f"the active platoon forged a complete item — definition, skin, behaviour code and "
        f"world placement — which the Foundry validated and folded into the Vault.",
        "",
    ]

    # Stage grounding (reuse the snowball knowledge vault where available)
    L += ["## 2. Vault Knowledge Grounding", ""]
    try:
        from core.stage_vault import vault_for_stage
        for stage in foundry.ITEM_STAGES:
            icon, label = _STAGE_META.get(stage, ("•", stage.title()))
            v = vault_for_stage(stage)
            doms = ", ".join(d["name"] for d in v.get("domains", [])) or "general"
            L.append(f"- {icon} **{label}** — vault domains: {doms}")
    except Exception:
        for stage in foundry.ITEM_STAGES:
            icon, label = _STAGE_META.get(stage, ("•", stage.title()))
            L.append(f"- {icon} **{label}**")
    L.append("")

    # Loot / artifact table
    L += ["## 3. Artifacts & Loot (forged gamefiles)", ""]
    L.append(_loot_table(items) if items else "_No gamefiles forged yet._")
    L.append("")

    # Palette board
    L += ["## 4. Palette Board", ""]
    for p in stats["palettes"][:8]:
        L.append(f"- **{p['name']}** · {p['count']} item(s)")
    L.append("")

    # Grade distribution
    L += ["## 5. Grade Distribution", ""]
    for g in stats["grade_histogram"]:
        bar = "█" * g["count"]
        L.append(f"- G{g['grade']} `{bar}` {g['count']}")
    L.append("")

    # Forging credits
    L += ["## 6. Forging Credits", ""]
    for a in stats["top_agents"]:
        L.append(f"- `{a['code']}` — {a['items']} item(s)")
    L.append("")

    return "\n".join(L)


def _llm_polish(gdd: str, genre: str) -> str:
    """Optional HYBRID pass — one LLM call appends a punchy elevator pitch.
    Best-effort: any failure leaves the deterministic GDD fully intact."""
    try:
        import asyncio
        from core.outcall_manager import OutcallManager
        prompt = (f"Write a punchy 2-sentence elevator pitch for this {genre} game GDD. "
                  f"Return ONLY the pitch text.\n\n{gdd[:1500]}")
        txt = asyncio.run(OutcallManager().generate_text(
            prompt, "You are a senior game pitch writer."))
        if txt and txt.strip():
            return gdd + "\n\n## 7. Elevator Pitch (LLM)\n\n" + txt.strip()[:400]
    except Exception:
        pass
    return gdd


def mount(build_id: str, seed: int = 0, forge_if_empty: bool = True,
          use_llm: bool = False, persist: bool = True) -> dict:
    """Generate the vault-grounded GDD from the gamefiles and MOUNT the build.

    If the Vault has no gamefiles yet and ``forge_if_empty`` is set, the Item
    Foundry is run first so the GDD is never empty.
    """
    data = read_gamefiles(build_id)
    items = data["items"]
    forged_now = False
    if not items and forge_if_empty:
        man = foundry.forge_build(
            build_id, vault_ctx={"genre": data["build"].get("genre") or "rpg"},
            seed=seed, persist=persist)
        forged_now = True
        # Prefer the freshly-forged (accepted) items so mount works even when
        # persist=False (nothing written back to the Vault to re-read).
        items = [it for st in man.get("stages", []) for it in st.get("items", [])
                 if (it.get("validation") or {}).get("accepted", True)]
        if persist:
            items = read_gamefiles(build_id)["items"] or items
        data["manifest"] = man

    gdd = compile_gdd(data["build"], items, data["manifest"])
    genre = data["build"].get("genre") or data["manifest"].get("genre") or "rpg"
    if use_llm and items:
        gdd = _llm_polish(gdd, genre)

    stats = foundry_stats(items)
    # Vault coverage across the item-bearing stages.
    covered = len({it.get("stage") for it in items})
    mount_doc = {
        "build_id": build_id,
        "seed": seed,
        "title": data["build"].get("title") or data["build"].get("name") or "Untitled",
        "genre": genre,
        "gdd": gdd,
        "gdd_chars": len(gdd),
        "stats": stats,
        "vault_gamefiles": len(items),
        "stages_covered": covered,
        "stages_total": len(foundry.ITEM_STAGES),
        "coverage_pct": round(100 * covered / len(foundry.ITEM_STAGES)),
        "forged_on_mount": forged_now,
        "mounted_at": time.time(),
    }

    if persist:
        try:
            from core.databases import get_sync_db
            col = get_sync_db()["galaxy_vault_mounts"]
            col.create_index([("build_id", 1)])
            col.update_one({"build_id": build_id}, {"$set": mount_doc}, upsert=True)
        except Exception:
            pass

    return mount_doc


def get_mount(build_id: str) -> dict | None:
    try:
        from core.databases import get_sync_db
        return get_sync_db()["galaxy_vault_mounts"].find_one(
            {"build_id": build_id}, {"_id": 0})
    except Exception:
        return None
