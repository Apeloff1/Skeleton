"""
╔════════════════════════════════════════════════════════════════════════╗
║  CONSTRUCT FORGE  &  MATERIAL FORGE                                      ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Forges LARGE composite assets — buildings, stores, cities, castles      ║
║  (kind="construct") and surface materials/textures (kind="material").    ║
║                                                                          ║
║  • 300+ era-appropriate PRESETS per era (7 eras → 2,100+), deterministic ║
║    and seed-reproducible, each with a parametric 3D geometry the client   ║
║    viewport renders + full colour/edit metadata.                          ║
║  • Optional HYBRID LLM pass (Claude Sonnet 4.6) folds a ≤20k-char user    ║
║    brief into palette / materials / VFX / descriptor.                     ║
║  • Full CRUD (save/edit/delete), built to store 100,000+ large assets     ║
║    (Mongo + indexes + pagination).                                        ║
║  • Vault connection: mount to a build's gamefiles, save assets to         ║
║    gamefiles, extract assets back out — like the other forges.            ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import hashlib
import os
import random
import time
from typing import Any

from core import eras as _eras

KINDS = ("construct", "material")
MAX_PROMPT = 20_000          # user LLM brief hard cap
ASSET_CAPACITY = 100_000     # large-asset store ceiling per kind

# ── Construct categories (large structures) ───────────────────────────────
_CONSTRUCT_CATS: list[str] = [
    "house", "cottage", "manor", "townhouse", "store", "shop", "market",
    "tavern", "inn", "smithy", "temple", "shrine", "church", "cathedral",
    "castle", "keep", "fortress", "tower", "watchtower", "barracks",
    "city_gate", "city_block", "walls", "bridge", "well", "fountain",
    "statue", "warehouse", "dock", "lighthouse", "windmill", "farmhouse",
    "barn", "palace", "arena", "library", "academy", "prison", "bank",
    "theater", "plaza", "guildhall",
]
_STYLES = ["rustic", "noble", "ruined", "ornate", "fortified", "humble",
           "grand", "weathered", "pristine", "gothic", "baroque", "minimal"]
_SIZE_CLASSES = ["small", "medium", "large", "huge", "monumental"]

# ── Material categories (surfaces) ────────────────────────────────────────
_MATERIAL_CATS: list[str] = [
    "stone", "brick", "wood", "oak", "pine", "marble", "granite", "sandstone",
    "limestone", "slate", "cobblestone", "clay", "terracotta", "thatch",
    "plaster", "stucco", "concrete", "iron", "steel", "bronze", "copper",
    "gold", "silver", "obsidian", "glass", "crystal", "ceramic", "tile",
    "leather", "canvas", "rope", "bone", "ice", "lava", "moss", "rust",
    "gilded_wood", "painted_plaster", "weathered_metal", "polished_marble",
    "rough_stone", "mossy_brick",
]
_FINISHES = ["matte", "polished", "rough", "weathered", "glossy", "satin",
             "burnished", "cracked", "mossy", "pristine", "aged", "wet"]

# Era-tinted base palettes so presets read as the right period.
_ERA_PALETTES: dict[str, list[str]] = {
    "8bit":    ["#5b3a1a", "#a05a2c", "#d9a066", "#3a5a40", "#8a8a8a", "#202020"],
    "16bit":   ["#6b4226", "#b5793a", "#e0b070", "#4d7c52", "#9aa0a6", "#2b2b2b"],
    "early3d": ["#6e5a48", "#8c6a4a", "#c0a080", "#5a6e58", "#7d8a96", "#3a3a3a"],
    "64bit":   ["#7a6a58", "#9a7a5a", "#cbb090", "#637a64", "#8a96a2", "#454545"],
    "earlyhd": ["#8a7a68", "#a98a66", "#d6c0a0", "#6e8a72", "#9aa6b2", "#505050"],
    "modern":  ["#9a8a78", "#b89a76", "#e6d2b0", "#7a9a80", "#aab6c2", "#5a5a5a"],
    "nextgen": ["#a89a88", "#c8aa86", "#f0e0c0", "#86aa90", "#bcc8d4", "#6a6a6a"],
}


def _rng(*parts: Any) -> random.Random:
    key = "|".join(str(p) for p in parts)
    return random.Random(int(hashlib.sha256(key.encode()).hexdigest()[:16], 16))


def _hex_shift(hex_color: str, rng: random.Random, amt: int = 22) -> str:
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        f = lambda v: max(0, min(255, v + rng.randint(-amt, amt)))  # noqa: E731
        return f"#{f(r):02x}{f(g):02x}{f(b):02x}"
    except Exception:
        return hex_color


def _palette(era_key: str, rng: random.Random, n: int = 5) -> list[str]:
    base = _ERA_PALETTES.get(era_key, _ERA_PALETTES["modern"])
    return [_hex_shift(rng.choice(base), rng) for _ in range(n)]


# ── Parametric 3D geometry for the client viewport (three.js parts) ────────
def _construct_geometry(category: str, palette: list[str], rng: random.Random,
                        size_class: str) -> list[dict]:
    """A list of parametric primitives {type,pos[x,y,z],size[w,h,d],color,rot}.
    Composed so each category reads as a recognisable structure in 3D."""
    scale = {"small": 0.7, "medium": 1.0, "large": 1.5,
             "huge": 2.2, "monumental": 3.2}.get(size_class, 1.0)
    wall = palette[0] if palette else "#9a8a78"
    roof = palette[1] if len(palette) > 1 else "#7a3a2a"
    trim = palette[2] if len(palette) > 2 else "#e0c090"
    accent = palette[3] if len(palette) > 3 else "#5a6e58"
    parts: list[dict] = []
    w = round(rng.uniform(2.5, 4.5) * scale, 2)
    d = round(rng.uniform(2.5, 4.5) * scale, 2)
    h = round(rng.uniform(2.2, 3.4) * scale, 2)
    # Base body
    parts.append({"type": "box", "pos": [0, h / 2, 0], "size": [w, h, d], "color": wall})
    # Roof variants
    if category in ("castle", "keep", "fortress", "tower", "watchtower", "lighthouse"):
        for i, (dx, dz) in enumerate([(-w / 2, -d / 2), (w / 2, -d / 2),
                                      (-w / 2, d / 2), (w / 2, d / 2)]):
            th = round(h * rng.uniform(1.2, 1.8), 2)
            parts.append({"type": "cylinder", "pos": [dx, th / 2, dz],
                          "size": [0.6 * scale, th, 0.6 * scale], "color": wall})
            parts.append({"type": "cone", "pos": [dx, th + 0.6 * scale, dz],
                          "size": [0.8 * scale, 1.2 * scale, 0.8 * scale], "color": roof})
    elif category in ("temple", "church", "cathedral", "palace", "library",
                       "academy", "bank", "theater", "guildhall"):
        parts.append({"type": "box", "pos": [0, h + 0.15, 0],
                      "size": [w + 0.6, 0.3, d + 0.6], "color": trim})
        cols = 4
        for c in range(cols):
            cx = -w / 2 + (c + 0.5) * (w / cols)
            parts.append({"type": "cylinder", "pos": [cx, h / 2, d / 2 + 0.3],
                          "size": [0.25 * scale, h, 0.25 * scale], "color": trim})
        if category in ("church", "cathedral", "temple"):
            parts.append({"type": "cone", "pos": [0, h + 1.4 * scale, 0],
                          "size": [1.0 * scale, 2.0 * scale, 1.0 * scale], "color": roof})
    else:
        # Pitched roof (houses, stores, taverns, barns…)
        parts.append({"type": "prism", "pos": [0, h + 0.7 * scale, 0],
                      "size": [w + 0.3, 1.4 * scale, d + 0.3], "color": roof})
    # Door + windows
    parts.append({"type": "box", "pos": [0, 0.6 * scale, d / 2 + 0.02],
                  "size": [0.7 * scale, 1.2 * scale, 0.1], "color": accent})
    nwin = rng.randint(2, 4)
    for i in range(nwin):
        wx = -w / 2 + (i + 1) * (w / (nwin + 1))
        parts.append({"type": "box", "pos": [wx, h * 0.65, d / 2 + 0.02],
                      "size": [0.45 * scale, 0.55 * scale, 0.08], "color": trim})
    return parts


def _material_geometry(category: str, palette: list[str], rng: random.Random) -> list[dict]:
    """A material swatch = a tiled plane preview the viewport renders."""
    base = palette[0] if palette else "#9a8a78"
    tiles = rng.choice([3, 4, 5])
    parts: list[dict] = [{"type": "plane", "pos": [0, 0, 0],
                          "size": [4, 0.1, 4], "color": base}]
    for r in range(tiles):
        for c in range(tiles):
            parts.append({
                "type": "tile",
                "pos": [round(-2 + (c + 0.5) * 4 / tiles, 2), 0.06,
                        round(-2 + (r + 0.5) * 4 / tiles, 2)],
                "size": [round(4 / tiles * 0.92, 2), 0.08, round(4 / tiles * 0.92, 2)],
                "color": _hex_shift(base, rng, 16),
            })
    return parts


def _preset(kind: str, era_key: str, idx: int) -> dict:
    """Deterministically build ONE preset for (kind, era, idx)."""
    era = _eras.get_era(era_key)
    cats = _CONSTRUCT_CATS if kind == "construct" else _MATERIAL_CATS
    mods = _STYLES if kind == "construct" else _FINISHES
    cat = cats[idx % len(cats)]
    mod = mods[(idx // len(cats)) % len(mods)]
    rng = _rng(kind, era["key"], cat, mod, idx)
    palette = _palette(era["key"], rng, 5 if kind == "construct" else 4)
    size_class = rng.choice(_SIZE_CLASSES)
    pid = "cst_" + hashlib.sha256(
        f"{kind}{era['key']}{cat}{mod}{idx}".encode()).hexdigest()[:10]
    poly = 0
    if era["max_poly"] > 0:
        poly = rng.randint(max(1, era["max_poly"] // 8), era["max_poly"])
    lo, hi = era["asset_kb_range"]
    label = f"{mod.replace('_', ' ').title()} {cat.replace('_', ' ').title()}"
    if kind == "construct":
        geometry = _construct_geometry(cat, palette, rng, size_class)
        materials = rng.sample(_MATERIAL_CATS, k=min(3, len(_MATERIAL_CATS)))
        footprint = {"w": geometry[0]["size"][0], "d": geometry[0]["size"][2],
                     "h": geometry[0]["size"][1]}
        descriptor = (f"A {size_class} {mod} {cat.replace('_', ' ')} in the "
                      f"{era['label']} style — built of {', '.join(materials)}.")
    else:
        geometry = _material_geometry(cat, palette, rng)
        materials = [cat]
        footprint = {"tiles": len(geometry) - 1}
        descriptor = (f"A {mod} {cat.replace('_', ' ')} surface tuned for the "
                      f"{era['label']} era.")
    return {
        "preset_id": pid, "kind": kind, "era": era["key"], "era_label": era["label"],
        "category": cat, "style": mod, "size_class": size_class if kind == "construct" else None,
        "name": label, "palette": palette, "materials": materials,
        "footprint": footprint, "geometry": geometry,
        "vfx": rng.choice(["none", "torchlight", "smoke", "banners", "fog",
                           "embers", "dust", "glow"]),
        "surface": {
            "roughness": round(rng.uniform(0.2, 0.95), 2),
            "metalness": round(rng.uniform(0.0, 0.9), 2),
            "emissive": rng.choice([0, 0, 0, round(rng.uniform(0.1, 0.6), 2)]),
            "tiling": rng.choice([1, 2, 4]),
        },
        "poly_budget": poly, "texture_res": era["texture_res"],
        "size_kb": rng.randint(lo, hi),
        "descriptor": descriptor,
    }


def presets_per_era(kind: str) -> int:
    """≥300 presets per era: every category × every style/finish modifier."""
    cats = _CONSTRUCT_CATS if kind == "construct" else _MATERIAL_CATS
    mods = _STYLES if kind == "construct" else _FINISHES
    return len(cats) * len(mods)


def list_presets(kind: str, era: str | None, offset: int = 0, limit: int = 60,
                 category: str | None = None) -> dict:
    kind = kind if kind in KINDS else "construct"
    era_spec = _eras.get_era(era)
    total = presets_per_era(kind)
    idxs = range(total)
    presets = [_preset(kind, era_spec["key"], i) for i in idxs]
    if category:
        presets = [p for p in presets if p["category"] == category]
    sliced = presets[offset: offset + max(1, min(limit, 300))]
    cats = sorted({p["category"] for p in presets})
    return {
        "kind": kind, "era": era_spec["key"], "era_label": era_spec["label"],
        "total": len(presets), "per_era": total, "offset": offset,
        "limit": limit, "categories": cats, "presets": sliced,
    }


# ── HYBRID — optional Claude Sonnet 4.6 enrich (≤20k brief) ────────────────
def _llm_enrich(spec: dict, user_prompt: str) -> dict | None:
    """Best-effort: fold the user's ≤20k brief into palette/materials/VFX/
    descriptor via Claude Sonnet 4.6. Any failure leaves the deterministic
    spec intact (true hybrid). Robust to both construct and universal specs."""
    user_prompt = (user_prompt or "").strip()[:MAX_PROMPT]
    if not user_prompt:
        # No creator brief → auto-derive one from the spec so the production
        # quality gate STILL runs for every LLM-enabled forge.
        _axes = ", ".join(f"{k}:{v}" for k, v in (spec.get("style_axes") or {}).items()) or "default"
        user_prompt = (
            f"Produce a polished, game-ready {spec.get('category') or spec.get('name') or 'asset'} "
            f"for the {spec.get('era_label') or spec.get('era') or 'modern'} era. "
            f"Honour these style axes: {_axes}. Make it cohesive and believable.")
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        import asyncio
        import json as _json
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        sysmsg = (
            "You are a world-class AAA game art director and senior technical "
            "artist shipping CONSUMER, store-ready assets. Elevate a single 3D "
            "game asset to spectacular production quality that matches the "
            "creator's brief AND reads as a cohesive, believable, hero-grade "
            "object. Aim for a visual-fidelity score of 95/100 or higher.\n"
            "Rules (every one is scored):\n"
            "• PALETTE: 5-6 valid hex colours forming a deliberate, harmonious "
            "ramp (base, secondary, accent, highlight, shadow) appropriate to "
            "the era, material and applied styles — no muddy or clashing tones.\n"
            "• MATERIALS: 3-6 concrete, tactile, real-world materials (e.g. "
            "'oxidised bronze', 'oiled walnut', 'frosted lead crystal') "
            "consistent with the finish / metal-grade / treatment chosen.\n"
            "• VFX: one short keyword (none, glow, embers, sparkle, fog, smoke).\n"
            "• DESCRIPTOR: a VERBOSE, consumer-polish art brief of ~128 words "
            "(minimum 110) a level designer & 3D artist can build from — cover "
            "silhouette & proportion, surface story & micro-detail, material "
            "breakdown, wear & edge damage, colour & lighting response, and "
            "mood/identity. Concrete and evocative, never generic.\n"
            "Honour every chosen style axis, skin and engraving/treatment. "
            "Respond with ONLY compact JSON: {\"name\":str,\"descriptor\":str,"
            "\"palette\":[hex,...up to 6],\"materials\":[str,...],"
            "\"vfx\":str,\"notes\":str}."
        )
        ctx = {k: spec.get(k) for k in (
            "name", "palette", "materials", "vfx", "descriptor", "surface",
            "skin_style", "style_axes", "treatment", "inscription")}
        prompt = (
            f"ERA: {spec.get('era_label') or spec.get('era') or 'modern'}. "
            f"KIND: {spec.get('kind') or spec.get('family') or 'asset'}. "
            f"CATEGORY: {spec.get('category') or spec.get('name') or 'asset'}. "
            f"GEOMETRY_PARTS: {len(spec.get('geometry') or [])}. "
            f"CURRENT_SPEC: {_json.dumps(ctx, default=str)[:2000]}. "
            f"CREATOR BRIEF (verbatim, ≤20k):\n{user_prompt}")

        import re as _re

        def _score_quality(d: dict) -> tuple[int, list[str]]:
            """Visual-fidelity score 0-100 + the reasons points were lost.
            Gate target = 95. Weights: palette 25, materials 25, descriptor 35,
            polish (vfx/name/notes) 15."""
            issues: list[str] = []
            score = 0
            pal = d.get("palette") if isinstance(d.get("palette"), list) else []
            valid = [c for c in pal if isinstance(c, str)
                     and _re.fullmatch(r"#?[0-9a-fA-F]{6}", c.strip())]
            if len(valid) >= 5:
                score += 25
            elif len(valid) >= 4:
                score += 18; issues.append("palette should be a 5-6 colour harmonious ramp (base/secondary/accent/highlight/shadow)")
            else:
                issues.append("palette needs 5-6 valid hex colours forming a deliberate harmony")
            mats = [m for m in (d.get("materials") or []) if isinstance(m, str) and len(m.strip()) > 2]
            if len(mats) >= 3:
                score += 25
            elif len(mats) >= 2:
                score += 16; issues.append("materials should list >=3 concrete tactile real-world materials")
            else:
                issues.append("materials needs >=3 concrete tactile real-world materials")
            words = len(str(d.get("descriptor") or "").split())
            if words >= 110:
                score += 35
            elif words >= 70:
                score += 24; issues.append(f"descriptor is {words} words — expand to a ~128-word consumer-polish art brief")
            elif words >= 25:
                score += 12; issues.append(f"descriptor is only {words} words — must be a verbose ~128-word art brief")
            else:
                issues.append("descriptor must be a verbose ~128-word art brief (silhouette, surface, materials, wear, lighting, mood)")
            polish = 0
            if str(d.get("vfx") or "").strip():
                polish += 5
            if str(d.get("name") or "").strip():
                polish += 5
            if len(str(d.get("notes") or "").split()) >= 6:
                polish += 5
            score += polish
            if polish < 15:
                issues.append("add a punchy name, a vfx keyword and a short notes line")
            return min(100, score), issues

        async def _run(feedback: str = "") -> str:
            sid = f"forge_{spec.get('preset_id') or spec.get('category') or 'x'}"
            chat = LlmChat(api_key=key, session_id=sid,
                           system_message=sysmsg).with_model("anthropic", "claude-sonnet-4-6")
            try:
                chat = chat.with_max_tokens(2200)  # verbose 128-word descriptors
            except Exception:
                pass
            msg = prompt if not feedback else (
                f"{prompt}\n\nYOUR PREVIOUS RESPONSE SCORED BELOW THE 95 FIDELITY "
                f"BAR. Fix these: {feedback}. Regenerate the FULL JSON at AAA, "
                f"consumer-ready quality. Respond with ONLY JSON.")
            return await chat.send_message(UserMessage(text=msg))

        def _run_sync(feedback: str = "") -> str:
            try:
                return asyncio.run(_run(feedback))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    return loop.run_until_complete(_run(feedback))
                finally:
                    loop.close()

        # ── Quality gate (target fidelity 95) ─────────────────────────────
        # Up to 3 attempts; re-prompt with the exact score gaps until the asset
        # clears 95/100 before it is delivered to the renderer. Keep the best.
        TARGET = 95
        best_data: dict | None = None
        best_score = -1
        best_issues: list[str] = []
        feedback = ""
        for _attempt in range(3):
            txt = _run_sync(feedback)
            if not txt:
                continue
            try:
                data = _json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
            except Exception:
                continue
            score, issues = _score_quality(data)
            if score > best_score:
                best_data, best_score, best_issues = data, score, issues
            if score >= TARGET:
                break
            feedback = "; ".join(issues)
        if best_data is None:
            return None
        data = best_data
        out: dict = {
            "llm_enriched": True,
            "fidelity_score": best_score,
            "quality_passed": best_score >= TARGET,
        }
        if best_issues and best_score < TARGET:
            out["quality_notes"] = best_issues
        if isinstance(data.get("palette"), list) and data["palette"]:
            out["palette"] = [str(c) for c in data["palette"][:6]]
        if isinstance(data.get("materials"), list) and data["materials"]:
            out["materials"] = [str(m) for m in data["materials"][:8]]
        for k in ("name", "descriptor", "vfx", "notes"):
            if data.get(k):
                out[k] = str(data[k])[:1600]
        return out
    except Exception:
        return None


# ── DB helpers ─────────────────────────────────────────────────────────────
def _col():
    from core.databases import get_sync_db
    col = get_sync_db()["galaxy_constructs"]
    try:
        col.create_index([("kind", 1), ("era", 1)])
        col.create_index([("build_id", 1), ("mounted", 1)])
        col.create_index([("construct_id", 1)], unique=True)
    except Exception:
        pass
    return col


def _new_id(kind: str) -> str:
    return ("mat_" if kind == "material" else "con_") + hashlib.sha256(
        f"{kind}{time.time()}{random.random()}".encode()).hexdigest()[:12]


def generate(kind: str, era: str | None, category: str | None = None,
             preset_id: str | None = None, user_prompt: str = "",
             use_llm: bool = False, seed: int | None = None) -> dict:
    """Build ONE construct/material from a preset (or category), optionally
    enriched by the Claude brief. Returns the full editable spec (not saved)."""
    kind = kind if kind in KINDS else "construct"
    era_spec = _eras.get_era(era)
    # Resolve a base preset.
    if seed is None:
        seed = random.randint(0, 10**6)
    if preset_id:
        total = presets_per_era(kind)
        base = next((_preset(kind, era_spec["key"], i) for i in range(total)
                     if _preset(kind, era_spec["key"], i)["preset_id"] == preset_id), None)
        base = base or _preset(kind, era_spec["key"], seed % presets_per_era(kind))
    else:
        cats = _CONSTRUCT_CATS if kind == "construct" else _MATERIAL_CATS
        idx = (cats.index(category) if category in cats else seed) % presets_per_era(kind)
        base = _preset(kind, era_spec["key"], idx)
    spec = dict(base)
    spec["llm_enriched"] = False
    if use_llm:
        enrich = _llm_enrich(spec, user_prompt)
        if enrich:
            spec.update(enrich)
    spec["user_prompt"] = (user_prompt or "")[:MAX_PROMPT]
    return spec


def save_construct(spec: dict, construct_id: str | None = None) -> dict:
    """Create or UPDATE (edit) a construct/material in the 100k-asset store."""
    kind = spec.get("kind", "construct")
    cid = construct_id or spec.get("construct_id") or _new_id(kind)
    col = _col()
    if not construct_id and not spec.get("construct_id"):
        if col.count_documents({"kind": kind}) >= ASSET_CAPACITY:
            raise ValueError(f"{kind} store full (capacity {ASSET_CAPACITY:,})")
    doc = {k: v for k, v in spec.items() if k != "_id"}
    doc.update({"construct_id": cid, "kind": kind,
                "updated_at": time.time(), "saved": True})
    doc.setdefault("created_at", time.time())
    col.update_one({"construct_id": cid}, {"$set": doc}, upsert=True)
    return {"construct_id": cid, "kind": kind, "saved": True}


def get_construct(construct_id: str) -> dict | None:
    return _col().find_one({"construct_id": construct_id}, {"_id": 0})


def update_construct(construct_id: str, patch: dict) -> dict | None:
    """Full edit — palette/colors/parts/name/surface/materials/geometry."""
    allowed = {"name", "palette", "materials", "geometry", "surface", "vfx",
               "descriptor", "footprint", "size_class", "category", "notes"}
    upd = {k: v for k, v in patch.items() if k in allowed}
    if not upd:
        return get_construct(construct_id)
    upd["updated_at"] = time.time()
    _col().update_one({"construct_id": construct_id}, {"$set": upd})
    return get_construct(construct_id)


def delete_construct(construct_id: str) -> bool:
    return _col().delete_one({"construct_id": construct_id}).deleted_count > 0


def list_constructs(kind: str | None = None, era: str | None = None,
                    build_id: str | None = None, mounted: bool | None = None,
                    offset: int = 0, limit: int = 60) -> dict:
    q: dict = {"saved": True}
    if kind:
        q["kind"] = kind
    if era:
        q["era"] = _eras.get_era(era)["key"]
    if build_id:
        q["build_id"] = build_id
    if mounted is not None:
        q["mounted"] = mounted
    col = _col()
    total = col.count_documents(q)
    rows = list(col.find(q, {"_id": 0}).skip(max(0, offset))
                .limit(max(1, min(limit, 300))))
    return {"total": total, "offset": offset, "limit": limit, "items": rows}


def count(kind: str | None = None) -> dict:
    col = _col()
    return {
        "construct": col.count_documents({"kind": "construct", "saved": True}),
        "material": col.count_documents({"kind": "material", "saved": True}),
        "capacity": ASSET_CAPACITY,
    }


# ── VAULT CONNECTION — mount / save-to-gamefiles / extract ─────────────────
def mount_to_build(construct_ids: list[str], build_id: str) -> dict:
    """Mount saved assets onto a build's gamefiles (vault connection)."""
    col = _col()
    n = col.update_many(
        {"construct_id": {"$in": construct_ids}},
        {"$set": {"build_id": build_id, "mounted": True, "mounted_at": time.time()}},
    ).modified_count
    # Mirror into the build's gamefile store so the final build picks them up.
    _write_gamefiles(build_id, construct_ids)
    return {"build_id": build_id, "mounted": n}


def _write_gamefiles(build_id: str, construct_ids: list[str]) -> None:
    try:
        from core.databases import get_sync_db
        gf = get_sync_db()["galaxy_construct_gamefiles"]
        gf.create_index([("build_id", 1), ("construct_id", 1)])
        col = _col()
        for cid in construct_ids:
            doc = col.find_one({"construct_id": cid}, {"_id": 0})
            if not doc:
                continue
            path = f"assets/{doc.get('kind', 'construct')}s/{doc.get('category', 'asset')}/{cid}.construct.json"
            gf.update_one(
                {"build_id": build_id, "construct_id": cid},
                {"$set": {"build_id": build_id, "construct_id": cid,
                          "path": path, "spec": doc, "kind": doc.get("kind"),
                          "written_at": time.time()}}, upsert=True)
    except Exception:
        pass


def save_to_gamefiles(build_id: str, construct_ids: list[str]) -> dict:
    """Persist asset specs as actual gamefiles in the Vault."""
    _write_gamefiles(build_id, construct_ids)
    from core.databases import get_sync_db
    n = get_sync_db()["galaxy_construct_gamefiles"].count_documents({"build_id": build_id})
    return {"build_id": build_id, "gamefiles": n}


def extract_from_build(build_id: str, into_library: bool = True) -> dict:
    """Extract asset specs FROM a build's gamefiles back into the library."""
    try:
        from core.databases import get_sync_db
        gf = get_sync_db()["galaxy_construct_gamefiles"]
        rows = list(gf.find({"build_id": build_id}, {"_id": 0}))
        extracted = []
        for r in rows:
            spec = r.get("spec") or {}
            extracted.append(spec)
            if into_library and spec.get("construct_id"):
                spec2 = dict(spec)
                spec2["build_id"] = None
                spec2["mounted"] = False
                save_construct(spec2, construct_id=spec.get("construct_id"))
        return {"build_id": build_id, "extracted": len(extracted),
                "assets": extracted}
    except Exception:
        return {"build_id": build_id, "extracted": 0, "assets": []}


# ── SNOWBALL INTEGRATION — forge a batch after the 100-phase gate ──────────
def forge_for_build(build_id: str, era: str | None = None, seed: int = 0,
                    construct_count: int = 12, material_count: int = 12,
                    config: dict | None = None, mount: bool = True,
                    seed_universal: bool = True) -> dict:
    """Snowball stage (runs AFTER the 100-phase questionnaire): forge a batch
    of era-correct constructs + materials, save them, mount to the Vault."""
    era_spec = _eras.get_era(era)
    made: dict[str, list[str]] = {"construct": [], "material": []}
    for kind, cnt in (("construct", construct_count), ("material", material_count)):
        per = presets_per_era(kind)
        for i in range(max(0, cnt)):
            base = _preset(kind, era_spec["key"], (seed + i * 7) % per)
            spec = dict(base)
            spec["build_id"] = build_id
            res = save_construct(spec)
            made[kind].append(res["construct_id"])
    all_ids = made["construct"] + made["material"]
    if mount and all_ids:
        mount_to_build(all_ids, build_id)
    # Universal auto-seed: mint a genre-themed batch of universal assets
    # (characters/flora/props/etc) so every build ships richer content.
    universal = {"total": 0}
    if seed_universal:
        try:
            from core import universal_forge as _uf
            genre = (config or {}).get("genre") or "rpg"
            universal = _uf.seed_for_build(build_id, era=era_spec["key"],
                                           genre=genre, seed=seed, mount=mount)
        except Exception:
            universal = {"total": 0, "error": True}
    return {
        "build_id": build_id, "era": era_spec["key"], "era_label": era_spec["label"],
        "constructs": len(made["construct"]), "materials": len(made["material"]),
        "universal": universal.get("total", 0),
        "universal_detail": universal,
        "mounted": mount, "construct_ids": made["construct"],
        "material_ids": made["material"],
        "presets_available": {"construct": presets_per_era("construct"),
                              "material": presets_per_era("material")},
    }


def build_assets(build_id: str, limit: int = 400) -> list[dict]:
    """Every forged asset mounted to a build — constructs + materials + ALL
    universal families. This is the COMBINED gamefiles set the worldforge and
    the 100-phase gates build from (single collection, single query)."""
    col = _col()
    return list(col.find({"build_id": build_id, "mounted": True}, {"_id": 0})
                .limit(max(1, min(limit, 1000))))


def forge_compose(build_id: str, era: str | None, items: list[dict],
                  seed: int = 0, mount: bool = True) -> dict:
    """Compose a THEMED settlement in one shot — e.g. items=[{category:'house',
    count:8},{category:'tower',count:4},{category:'walls',count:1},
    {category:'castle',count:1}]. Each item forges `count` style-varied assets
    of that category, saves them, and mounts the batch onto the build's Vault."""
    era_spec = _eras.get_era(era)
    made: dict[str, list[str]] = {"construct": [], "material": []}
    composed: list[dict] = []
    for it in items or []:
        kind = it.get("kind") if it.get("kind") in KINDS else "construct"
        cat = it.get("category")
        cnt = max(0, min(int(it.get("count", 1) or 0), 200))
        if cnt <= 0:
            continue
        cats = _CONSTRUCT_CATS if kind == "construct" else _MATERIAL_CATS
        base = cats.index(cat) if cat in cats else 0
        for i in range(cnt):
            # vary the STYLE/finish while keeping the chosen category fixed
            idx = (base + i * len(cats)) % presets_per_era(kind)
            spec = dict(_preset(kind, era_spec["key"], idx))
            spec["build_id"] = build_id
            made[kind].append(save_construct(spec)["construct_id"])
        composed.append({"category": cat, "kind": kind, "count": cnt})
    all_ids = made["construct"] + made["material"]
    if mount and all_ids:
        mount_to_build(all_ids, build_id)
    return {
        "build_id": build_id, "era": era_spec["key"], "era_label": era_spec["label"],
        "composed": composed, "total": len(all_ids),
        "constructs": len(made["construct"]), "materials": len(made["material"]),
        "mounted": mount,
    }
