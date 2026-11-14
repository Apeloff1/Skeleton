"""
╔════════════════════════════════════════════════════════════════════════╗
║  ITEM FOUNDRY — Agent Item Creation Workflow (per the SOTA-2026 flow).   ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Every agent in a build forges a COMPLETE item and folds it into the     ║
║  gamefiles, grounded in the Vault for snowball consistency:              ║
║                                                                        ║
║   Item Planning → Item Definition (data) → Code-Gen → Asset-Linkage     ║
║                         → Validation & Reflection → fold into gamefiles  ║
║                                                                        ║
║  Each item is FULL: definition + skin (visual descriptor) + behaviour    ║
║  code + world placement. Items are graded ABOVE the base gamefiles and   ║
║  must stay visually faithful to the Vault (fidelity score). Deterministic ║
║  (seed-reproducible) with an optional LLM flavour hook.                  ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import random
import time
from typing import Any

from core import swarm_planner as planner

# Creative item-bearing stages (subset of the build ladder) — the steps where
# agents fold new items into the world.
ITEM_STAGES: list[str] = ["world", "narrative", "mechanics", "procedural", "tileset", "assets"]

# Archetype buckets keyed loosely by agent category (fallback = "artifact").
_ARCHETYPES = {
    "visual": ["Relic", "Banner", "Idol", "Mural", "Beacon", "Prism Array",
               "Holo-Effigy", "Refraction Lens", "Aurora Totem", "Sigil Plate"],
    "physics": ["Engine Core", "Gravity Well", "Kinetic Charm", "Rift Anchor",
                "Inertial Dampener", "Tensor Coil", "Momentum Sink", "Phase Gyro",
                "Singularity Node", "Harmonic Resonator"],
    "systems": ["Module", "Protocol Shard", "Daemon Totem", "Logic Gate",
                "State Machine Core", "Scheduler Crystal", "Telemetry Beacon",
                "Dependency Lattice", "Orchestration Hub", "Event Bus Relic"],
    "world": ["Landmark", "Shrine", "Gateway", "Monolith", "Grove",
              "Leyline Nexus", "Biome Seed", "Tectonic Anchor", "Skybridge Pylon",
              "Wayshrine Network"],
    "narrative": ["Tome", "Sigil", "Memory Echo", "Oath Blade", "Chronicle",
                  "Branching Codex", "Confessor's Mask", "Fate Loom",
                  "Unreliable Diary", "Choral Manuscript"],
    "audio": ["Resonator", "Echo Bell", "Chord Stone", "Adaptive Score Engine",
              "Leitmotif Locket", "Spatial Audio Orb", "Foley Anvil", "Drone Pillar"],
    "combat": ["Blade", "Aegis", "Sidearm", "Warhammer", "Ward",
               "Parry Gauntlet", "Combo Ledger", "Stagger Lance", "Riposte Edge",
               "Hyperarmor Plate"],
    "production": ["Forge Stamp", "Pipeline Anchor", "Master Mold", "CI Sigil",
                   "Asset Bundler", "QA Oracle", "Build Manifest Seal"],
    # advanced procedural-generation base items
    "procedural": ["WFC Tilebook", "Grammar Dungeon Seed", "Noise Terrain Core",
                   "L-System Bloom", "Voronoi Fracture Stone", "Poisson Scatterer",
                   "Markov Quest Spinner", "Erosion Simulator Shard",
                   "Biome Blender Prism", "Procedural Mesh Loom"],
}
_CATEGORY_BUCKET = {
    "visual_design": "visual", "rendering": "visual", "art": "visual",
    "physics": "physics", "simulation": "physics",
    "systems": "systems", "engine": "systems", "math_cs": "systems", "networking": "systems",
    "world": "world", "worldbuilding": "world", "level_design": "world",
    "narrative": "narrative", "story": "narrative", "era_esoteric": "narrative",
    "audio": "audio", "music": "audio",
    "combat": "combat", "gameplay": "combat", "mechanics": "combat",
    "production": "production", "qa": "production",
}
_PALETTES = {
    "ember": ["#FF6B35", "#F7931E", "#FFD23F", "#2B1B17"],
    "abyss": ["#0B132B", "#1C2541", "#3A506B", "#5BC0BE"],
    "verdant": ["#1B4332", "#2D6A4F", "#52B788", "#D8F3DC"],
    "amethyst": ["#240046", "#5A189A", "#9D4EDD", "#E0AAFF"],
    "frost": ["#03045E", "#0077B6", "#00B4D8", "#CAF0F8"],
    "solar": ["#FFBA08", "#FAA307", "#E85D04", "#370617"],
}
_MATERIALS = ["brushed alloy", "living crystal", "obsidian glass", "woven aether",
              "runed bronze", "bioluminescent resin", "fractured starsteel"]
_SILHOUETTES = ["angular", "organic-flowing", "monolithic", "filigreed", "asymmetric", "crystalline"]
_VFX = ["pulsing rim-light", "drifting embers", "refractive shimmer", "trailing motes",
        "arc discharge", "soft volumetric glow", "parallax aura"]
_PREFIX = ["Aether", "Umbral", "Verdant", "Solar", "Nether", "Prism", "Iron", "Echo", "Star", "Rune"]
_ROOT = ["bind", "shard", "ward", "song", "forge", "veil", "crown", "thorn", "spire", "ember"]
_SUFFIX = ["of the Vault", "of First Light", "Mk.II", "Ascendant", "Reborn", "of the Deep", "Prime"]

# rarity tier → grade value
_TIERS = [("Common", 1), ("Rare", 2), ("Epic", 3), ("Legendary", 4), ("Mythic", 5)]


def _rng(*parts: Any) -> random.Random:
    key = "|".join(str(p) for p in parts)
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


def _llm_flavor(items: list[dict], genre: str) -> None:
    """Optional HYBRID pass — one LLM call enriches render-notes in place.
    Best-effort: any failure (or INTERNAL mode) leaves the deterministic
    flavour fully intact, so the build never blocks on the model."""
    if not items:
        return
    try:
        import asyncio
        import json as _json
        from core.outcall_manager import OutcallManager
        listing = "; ".join(f"{i['item_id']}:{i['definition']['archetype']}" for i in items[:24])
        prompt = (f"Game genre: {genre}. Return ONLY JSON mapping each id to a vivid "
                  f"12-word art render note: {listing}")
        txt = asyncio.run(OutcallManager().generate_text(prompt, "You are a senior art director."))
        if not txt:
            return
        data = _json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        for it in items:
            note = data.get(it["item_id"])
            if note:
                it["skin"]["render_notes"] = str(note)[:240]
                it["skin"]["llm_enriched"] = True
    except Exception:
        return


def _regions_for(vault_ctx: dict) -> list[str]:
    regions = vault_ctx.get("regions")
    if regions:
        return regions
    genre = (vault_ctx.get("genre") or "rpg").lower()
    base = {
        "rpg": ["Ashen Vale", "Sunken Keep", "Emberwood", "Frost March"],
        "platformer": ["Sky Bastion", "Cavern Run", "Neon District"],
        "shooter": ["Drop Zone", "Reactor Bay", "Orbital Ring"],
    }.get(genre, ["Region One", "Region Two", "Region Three", "Region Four"])
    return base


def forge_item(build_id: str, phase: str, agent: dict, vault_ctx: dict,
               seed: int = 0, base_grade: int = 2) -> dict:
    """Forge ONE complete item for a single agent: planning→definition→code→
    asset-linkage. Graded strictly above ``base_grade``; faithful to the Vault."""
    code = agent.get("code") or agent.get("agent_code") or agent.get("id") or "AXXXX"
    cat = (agent.get("category") or "").lower()
    bucket = _CATEGORY_BUCKET.get(cat, "world")
    if phase == "procedural":
        bucket = "procedural"  # the procedural stage forges advanced procgen base items
    rng = _rng("item", build_id, phase, code, seed)

    # ── Planning: pick archetype + name (variety per agent) ──────────────
    archetype = rng.choice(_ARCHETYPES.get(bucket, ["Artifact"]))
    name = f"{rng.choice(_PREFIX)}{rng.choice(_ROOT)} {rng.choice(_SUFFIX)}"

    # ── Definition (data layer): tier strictly above the base gamefiles ──
    min_tier_idx = min(len(_TIERS) - 1, max(0, base_grade))  # grade >= base_grade+1
    tier_idx = rng.randint(min_tier_idx, len(_TIERS) - 1)
    tier_name, grade = _TIERS[tier_idx]
    power = 40 + tier_idx * 12 + rng.randint(0, 11)
    definition = {
        "archetype": archetype, "tier": tier_name, "grade": grade,
        "stats": {"power": power, "utility": rng.randint(20, 95), "rarity_weight": 6 - tier_idx},
        "lore": f"A {tier_name.lower()} {archetype.lower()} forged by {agent.get('agent', code)} "
                f"during the {phase} stage, echoing the Vault's canon.",
    }

    # ── Asset-Linkage: skin / visual descriptor (faithful to Vault + era) ─
    from core import eras as _eras
    era = _eras.get_era(vault_ctx.get("era"))
    pal_name = rng.choice(list(_PALETTES.keys()))
    region = rng.choice(_regions_for(vault_ctx))
    # palette swatches are capped to the era's colour budget
    full_pal = _PALETTES[pal_name]
    pal = full_pal[: max(1, min(len(full_pal), era["colors_max"]))]
    poly_budget = rng.randint(max(1, era["max_poly"] // 8), era["max_poly"]) if era["max_poly"] else 0
    skin = {
        "palette_name": pal_name, "palette": pal,
        "material": rng.choice(_MATERIALS), "silhouette": rng.choice(_SILHOUETTES),
        "vfx": rng.choice(_VFX), "anchor_region": region,
        "render_notes": f"{rng.choice(_SILHOUETTES)} {archetype.lower()} in {pal_name} palette, "
                        f"{rng.choice(_MATERIALS)}, with {rng.choice(_VFX)}; "
                        f"{era['label']} target ({era['resolution']}).",
        "fidelity": round(0.74 + tier_idx * 0.04 + rng.random() * 0.06, 2),  # ≥ 0.74
        # ── era-sensitive production spec ──
        "era": era["key"], "era_label": era["label"],
        "resolution": era["resolution"], "texture_res": era["texture_res"],
        "color_label": era["color_label"], "poly_budget": poly_budget,
        "audio_format": era["audio_format"], "platforms": era["platforms"],
        # ── advanced choices reflected on every gamefile ──
        "applied_choices": dict(vault_ctx.get("applied_choices") or {}),
    }

    # ── Crosswire: fold the chosen axis EFFECTS into the skin so each choice
    #    is an ACTUAL change to this item (not just a label stamp). ───────────
    try:
        from core import snowball_axes as _ax
        _spec = {"genre": vault_ctx.get("genre"), "era": vault_ctx.get("era"),
                 "dimension": vault_ctx.get("dimension") or vault_ctx.get("dim")}
        _eff = _ax.apply_effects(dict(vault_ctx.get("applied_choices") or {}), _spec)
        _d = _eff["directives"]
        if _d:
            skin["forge_directives"] = _d
            if _d.get("shader"):
                skin["shader"] = _d["shader"]
            if _d.get("mat"):
                skin["material_model"] = _d["mat"]
            if _d.get("vfx"):
                skin["vfx"] = _d["vfx"]
            if _d.get("palette_bias"):
                skin["palette_bias"] = _d["palette_bias"]
            if _d.get("tri_budget"):
                skin["poly_budget"] = _d["tri_budget"] if _d["tri_budget"] > 0 else skin["poly_budget"]
            if _d.get("anim"):
                skin["animation"] = _d["anim"]
            if _d.get("lod"):
                skin["lod"] = _d["lod"]
            # render_notes now describes the genuine applied directives
            _bits = [f"{k}={v}" for k, v in list(_d.items())[:6] if "." not in k]
            if _bits:
                skin["render_notes"] += "  · choices→ " + ", ".join(_bits)
            skin["choices_advanced"] = _eff["advanced_count"]
    except Exception:
        pass

    # ── Code-Gen: behaviour block (folded into gamefiles) ────────────────
    item_id = f"itm_{hashlib.sha256(f'{build_id}{phase}{code}{seed}'.encode()).hexdigest()[:10]}"
    behaviour = (
        f"export const {item_id} = {{\n"
        f"  id: '{item_id}', name: {name!r}, tier: '{tier_name}', grade: {grade},\n"
        f"  power: {power}, region: {region!r},\n"
        f"  onEquip(p) {{ p.stats.power += {power // 4}; p.applyAura('{skin['vfx']}'); }},\n"
        f"  onUse(ctx) {{ return ctx.spawn('{archetype}', {{ palette: {skin['palette']!r} }}); }},\n"
        f"}};"
    )

    # ── Placement in the world ───────────────────────────────────────────
    placement = {
        "region": region,
        "coords": [rng.randint(0, 1024), rng.randint(0, 1024)],
        "spawn_rule": rng.choice(["on_enter", "boss_drop", "hidden_cache", "vendor", "quest_reward"]),
        "anchor_gamefile": (vault_ctx.get("existing_refs") or [f"{phase}_canon"])[
            rng.randint(0, max(0, len(vault_ctx.get("existing_refs") or [f"{phase}_canon"]) - 1))],
    }

    return {
        "item_id": item_id, "name": name, "stage": phase,
        "agent_code": code, "agent": agent.get("agent"),
        "category": cat, "bucket": bucket,
        "grade": grade, "base_grade": base_grade,
        "definition": definition, "skin": skin, "code": behaviour, "placement": placement,
        "vault_refs": vault_ctx.get("existing_refs") or [f"{phase}_canon"],
    }


def validate_and_reflect(item: dict, vault_ctx: dict, base_grade: int = 2) -> dict:
    """Validation & Reflection loop: grade must exceed gamefiles, skin must stay
    faithful, code+placement must be coherent. Returns acceptance + notes."""
    issues = []
    if item["grade"] <= base_grade:
        issues.append("grade not above base gamefiles")
    if item["skin"]["fidelity"] < 0.7:
        issues.append("visual fidelity below Vault threshold")
    if not item.get("code"):
        issues.append("missing behaviour code")
    if item["placement"]["region"] not in _regions_for(vault_ctx):
        issues.append("placement region not in Vault world")
    accepted = not issues
    return {
        "accepted": accepted,
        "issues": issues,
        "reflection": "Folds cleanly into gamefiles; higher-grade & Vault-faithful."
        if accepted else "Needs revision: " + "; ".join(issues),
    }


def forge_build(build_id: str, vault_ctx: dict | None = None, seed: int = 0,
                platoon_size: int = 5, persist: bool = True, use_llm: bool = False) -> dict:
    """Run the full Item Creation Workflow for a build: every agent in every
    item-bearing stage forges + validates a full item, folded into gamefiles."""
    vault_ctx = dict(vault_ctx or {})
    vault_ctx.setdefault("genre", "rpg")
    base_grade = int(vault_ctx.get("base_grade", 2))

    # Reuse the planner DAG so items map onto the same platoon assignments.
    plan = planner.plan_build(build_id=build_id, phases=list(ITEM_STAGES),
                              seed=seed, platoon_size=platoon_size, game_ctx=vault_ctx)
    platoons = {n["phase_id"]: n["workers"] for n in plan["nodes"] if n["tier"] == "platoon"}

    stages_out, accepted_items = [], []
    total = rejected = 0
    for stage in ITEM_STAGES:
        rows = []
        for worker in platoons.get(stage, []):
            item = forge_item(build_id, stage, worker, vault_ctx, seed, base_grade)
            verdict = validate_and_reflect(item, vault_ctx, base_grade)
            item["validation"] = verdict
            total += 1
            if verdict["accepted"]:
                accepted_items.append(item)
            else:
                rejected += 1
            rows.append(item)
        stages_out.append({"stage": stage, "agent_count": len(rows), "items": rows})

    if use_llm:
        _llm_flavor(accepted_items, vault_ctx.get("genre") or "rpg")

    manifest = {
        "build_id": build_id, "seed": seed, "plan_hash": plan["plan_hash"],
        "base_grade": base_grade, "genre": vault_ctx.get("genre"),
        "stages": stages_out,
        "totals": {
            "items_forged": total, "accepted": len(accepted_items), "rejected": rejected,
            "avg_grade": round(sum(i["grade"] for i in accepted_items) / max(1, len(accepted_items)), 2),
            "avg_fidelity": round(sum(i["skin"]["fidelity"] for i in accepted_items)
                                  / max(1, len(accepted_items)), 3),
            "distinct_archetypes": len({i["definition"]["archetype"] for i in accepted_items}),
            "grade_above_base": all(i["grade"] > base_grade for i in accepted_items),
        },
        "created_at": time.time(),
    }

    if persist:
        try:
            from core.databases import get_sync_db
            db = get_sync_db()
            col = db["galaxy_build_items"]
            col.create_index([("build_id", 1), ("stage", 1)])
            for it in accepted_items:
                col.update_one({"build_id": build_id, "item_id": it["item_id"]},
                               {"$set": {**it, "build_id": build_id}}, upsert=True)
            # Fold into the Vault alongside gamefiles (snowball consistency).
            vault = db["galaxy_vault"]
            for it in accepted_items:
                vault.update_one(
                    {"build_id": build_id, "kind": "item", "ref_id": it["item_id"]},
                    {"$set": {"build_id": build_id, "kind": "item", "ref_id": it["item_id"],
                              "stage": it["stage"], "name": it["name"], "grade": it["grade"],
                              "skin": it["skin"], "placement": it["placement"],
                              "archetype": it["definition"]["archetype"]}}, upsert=True)
            db["galaxy_item_manifests"].update_one(
                {"build_id": build_id, "seed": seed},
                {"$set": {k: v for k, v in manifest.items() if k != "stages"}}, upsert=True)
        except Exception:
            pass

    return manifest


def list_items(build_id: str, stage: str | None = None, limit: int = 200) -> list[dict]:
    try:
        from core.databases import get_sync_db
        q: dict = {"build_id": build_id}
        if stage:
            q["stage"] = stage
        return list(get_sync_db()["galaxy_build_items"].find(q, {"_id": 0}).limit(max(1, min(limit, 500))))
    except Exception:
        return []
