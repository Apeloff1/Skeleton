"""
═══════════════════════════════════════════════════════════════════════════
 AGENT KNOWLEDGE-BASE API
─────────────────────────────────────────────────────────────────────────
 Unified read API over the new agent-facing knowledge collections:
   • patch_notes        — 25+ curated meta-defining patches across top games
   • github_code_refs   — 25+ curated open-license code snippets / patterns
   • language_classes   — 451 programming-language curricula (existing)

 The Galaxy Studio agent pipeline calls these endpoints when generating,
 refactoring, bug-fixing or patching game code so the output is grounded
 in real industry-standard references — the system stays SOTA + offline.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import logging
from typing import Optional
from fastapi import APIRouter, Query
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
from dotenv import load_dotenv
from pathlib import Path
import os

load_dotenv(Path(__file__).parent.parent / '.env')

log = logging.getLogger("agent.knowledge")

router = APIRouter(prefix="/api/knowledge", tags=["Agent Knowledge"])
_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get("DB_NAME", "codedock")]
PROJ = {"_id": 0}


@router.get("/stats")
async def kb_stats():
    """Top-line counts that the agent can read to know what's available."""
    return {
        "patch_notes":              await _db.patch_notes.count_documents({}),
        "github_code_refs":         await _db.github_code_refs.count_documents({}),
        "language_classes":         await _db.language_classes.count_documents({}),
        "code_synthesis_templates": await _db.code_synthesis_templates.count_documents({}),
        "code_diagnostics_rules":   await _db.code_diagnostics_rules.count_documents({}),
        "procgen_recipes":          await _db.procgen_recipes.count_documents({}),
        "content_catalogues":       await _db.content_catalogues.count_documents({}),
        "game_design_patterns":     await _db.game_design_patterns.count_documents({}),
        "game_balance_curves":      await _db.game_balance_curves.count_documents({}),
        "engine_api_schemas":       await _db.engine_api_schemas.count_documents({}),
        "gamestate_schemas":        await _db.gamestate_schemas.count_documents({}),
        "qa_oracles":               await _db.qa_oracles.count_documents({}),
        "ai_generative_weights":    await _db.ai_generative_weights.count_documents({}),
        "build_recipes":            await _db.build_recipes.count_documents({}),
        "input_haptics":            await _db.input_haptics.count_documents({}),
        "physics_materials_sim":    await _db.physics_materials_sim.count_documents({}),
        "audio_dsp":                await _db.audio_dsp.count_documents({}),
        "security_crypto":          await _db.security_crypto.count_documents({}),
        "legal_compliance":         await _db.legal_compliance.count_documents({}),
        "variation_mutation":       await _db.variation_mutation.count_documents({}),
        "emotional_dialogue":       await _db.emotional_dialogue.count_documents({}),
        "historical_meta":          await _db.historical_meta.count_documents({}),
        "director_pacing":          await _db.director_pacing.count_documents({}),
        "visual_juice":             await _db.visual_juice.count_documents({}),
        "cognitive_psychographics": await _db.cognitive_psychographics.count_documents({}),
        "deep_lore":                await _db.deep_lore.count_documents({}),
        "ecosystems_biology":       await _db.ecosystems_biology.count_documents({}),
        "publishing_assets":        await _db.publishing_assets.count_documents({}),
        # ── Phase 4 ───────────────────────────────────────────────────
        "code_similarity_logic":      await _db.code_similarity_logic.count_documents({}),
        "asset_engine_theft":         await _db.asset_engine_theft.count_documents({}),
        "game_playing_logic_clones":  await _db.game_playing_logic_clones.count_documents({}),
        "ast_detection":              await _db.ast_detection.count_documents({}),
        "mechanic_legal_paradox":     await _db.mechanic_legal_paradox.count_documents({}),
        "stylometric_fingerprint":    await _db.stylometric_fingerprint.count_documents({}),
        "academic_frameworks":        await _db.academic_frameworks.count_documents({}),
        "linting_formatters":         await _db.linting_formatters.count_documents({}),
        "agnostic_content_index":     await _db.agnostic_content_index.count_documents({}),
        "training_recipes":           await _db.training_recipes.count_documents({}),
        "scraper_jobs":               await _db.scraper_jobs.count_documents({}),
        "ready": True,
    }


# ─── Generic list endpoint for the 14 new collections ────────────────
_EXT_COLLS = {
    "input-haptics":         ("input_haptics", ["device","category","action"]),
    "physics-materials":     ("physics_materials_sim", ["category","name","sim_kind","engine"]),
    "audio-dsp":             ("audio_dsp", ["category","genre","fx","preset","motif"]),
    "security-crypto":       ("security_crypto", ["category","name","genre"]),
    "legal-compliance":      ("legal_compliance", ["rule","region"]),
    "variation-mutation":    ("variation_mutation", ["axis","distribution","intensity"]),
    "emotional-dialogue":    ("emotional_dialogue", ["emotion","intensity","context"]),
    "historical-meta":       ("historical_meta", ["category","era"]),
    "director-pacing":       ("director_pacing", ["category","beat","rule","genre"]),
    "visual-juice":          ("visual_juice", ["category","effect","intensity","beat"]),
    "cognitive-psychographics":("cognitive_psychographics", ["category","archetype","factor","intensity"]),
    "deep-lore":             ("deep_lore", ["category","mythology","archetype","cosmology","faction","element"]),
    "ecosystems-biology":    ("ecosystems_biology", ["category","species","biome","interaction"]),
    "publishing-assets":     ("publishing_assets", ["category","storefront","kind","locale"]),
    # ── Phase 4 ───────────────────────────────────────────────────
    "code-similarity-logic": ("code_similarity_logic", ["technique","language"]),
    "asset-engine-theft":    ("asset_engine_theft", ["signature","engine"]),
    "game-playing-logic-clones":("game_playing_logic_clones", ["original","clone","aspect"]),
    "ast-detection":         ("ast_detection", ["detector","language"]),
    "mechanic-legal-paradox":("mechanic_legal_paradox", ["case","facts","outcome"]),
    "stylometric-fingerprint":("stylometric_fingerprint", ["feature","language"]),
    "academic-frameworks":   ("academic_frameworks", ["name","author"]),
    "linting-formatters":    ("linting_formatters", ["language","tool"]),
    "agnostic-content-index":("agnostic_content_index", ["source","license"]),
    "training-recipes":      ("training_recipes", ["recipe"]),
    "scraper-jobs":          ("scraper_jobs", ["name","cadence","enabled"]),
}

@router.get("/collections")
async def list_collections():
    """List every agent-knowledge collection and its current row count.
    Used by the frontend Agent Codex modal to enumerate browsable DBs."""
    base = {
        "patch_notes":              await _db.patch_notes.count_documents({}),
        "github_code_refs":         await _db.github_code_refs.count_documents({}),
        "language_classes":         await _db.language_classes.count_documents({}),
        "code_synthesis_templates": await _db.code_synthesis_templates.count_documents({}),
        "code_diagnostics_rules":   await _db.code_diagnostics_rules.count_documents({}),
        "procgen_recipes":          await _db.procgen_recipes.count_documents({}),
        "content_catalogues":       await _db.content_catalogues.count_documents({}),
        "game_design_patterns":     await _db.game_design_patterns.count_documents({}),
        "game_balance_curves":      await _db.game_balance_curves.count_documents({}),
        "engine_api_schemas":       await _db.engine_api_schemas.count_documents({}),
        "gamestate_schemas":        await _db.gamestate_schemas.count_documents({}),
        "qa_oracles":               await _db.qa_oracles.count_documents({}),
        "ai_generative_weights":    await _db.ai_generative_weights.count_documents({}),
        "build_recipes":            await _db.build_recipes.count_documents({}),
    }
    for slug, (coll, _) in _EXT_COLLS.items():
        base[coll] = await _db[coll].count_documents({})
    rows = [{"slug": k.replace("_", "-"), "collection": k, "count": v} for k, v in base.items()]
    return {"collections": rows, "total_rows": sum(v for v in base.values()), "ready": True}


@router.get("/c/{slug}")
async def browse_collection(
    slug: str,
    q: Optional[str] = None,
    limit: int = Query(30, le=100),
    skip: int = Query(0, ge=0),
):
    """Generic browse endpoint for any of the 14 extension collections."""
    if slug not in _EXT_COLLS:
        return {"error": f"unknown collection slug {slug}", "valid": list(_EXT_COLLS.keys())}
    coll_name, fields = _EXT_COLLS[slug]
    mongo_q: dict = {}
    if q:
        regex = {"$regex": q, "$options": "i"}
        mongo_q = {"$or": [{"description": regex}, {"tags": regex}] + [{f: regex} for f in fields]}
    rows = await _db[coll_name].find(mongo_q, PROJ).skip(skip).limit(limit).to_list(limit)
    total = await _db[coll_name].count_documents(mongo_q)
    return {"slug": slug, "collection": coll_name, "rows": rows, "total": total, "showing": len(rows), "skip": skip}


# ─── Game-state schemas ─────────────────────────────────────────────
@router.get("/gamestate-schemas")
async def list_gamestate(
    engine: Optional[str] = None,
    genre: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q: dict = {}
    if engine: q["engine"] = engine
    if genre:  q["genre"] = genre
    if kind:   q["kind"] = kind
    rows = await _db.gamestate_schemas.find(q, PROJ).limit(limit).to_list(limit)
    return {"schemas": rows, "total": await _db.gamestate_schemas.count_documents(q)}


# ─── QA oracles ─────────────────────────────────────────────────────
@router.get("/qa-oracles")
async def list_qa(
    invariant: Optional[str] = None,
    genre: Optional[str] = None,
    kind: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q: dict = {}
    if invariant: q["invariant_name"] = invariant
    if genre:     q["genre"] = genre
    if kind:      q["kind"] = kind
    if severity:  q["severity"] = severity
    rows = await _db.qa_oracles.find(q, PROJ).limit(limit).to_list(limit)
    return {"oracles": rows, "total": await _db.qa_oracles.count_documents(q)}


# ─── AI generative weight recipes ───────────────────────────────────
@router.get("/ai-weights")
async def list_ai_weights(
    strategy: Optional[str] = None,
    domain: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q: dict = {}
    if strategy:   q["strategy"] = strategy
    if domain:     q["domain"] = domain
    if difficulty: q["difficulty"] = difficulty
    rows = await _db.ai_generative_weights.find(q, PROJ).limit(limit).to_list(limit)
    return {"weights": rows, "total": await _db.ai_generative_weights.count_documents(q)}


# ─── Build recipes ──────────────────────────────────────────────────
@router.get("/build-recipes")
async def list_build_recipes(
    engine: Optional[str] = None,
    platform: Optional[str] = None,
    mode: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q: dict = {}
    if engine:   q["engine"] = engine
    if platform: q["platform"] = platform
    if mode:     q["mode"] = mode
    rows = await _db.build_recipes.find(q, PROJ).limit(limit).to_list(limit)
    return {"recipes": rows, "total": await _db.build_recipes.count_documents(q)}


# ─── Code Synthesis Templates ───────────────────────────────────────
@router.get("/templates")
async def list_templates(
    kind: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = Query(50, le=200),
    skip:  int = Query(0, ge=0),
):
    q: dict = {}
    if kind:     q["kind"] = kind
    if language: q["language"] = {"$regex": f"^{language}$", "$options": "i"}
    rows = await _db.code_synthesis_templates.find(q, PROJ).skip(skip).limit(limit).to_list(limit)
    return {"templates": rows, "total": await _db.code_synthesis_templates.count_documents(q)}


# ─── Code Diagnostics Rules ─────────────────────────────────────────
@router.get("/diagnostics")
async def list_diagnostics(
    rule: Optional[str] = None,
    language: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q: dict = {}
    if rule:     q["rule"] = rule
    if language: q["language"] = {"$regex": f"^{language}$", "$options": "i"}
    if severity: q["severity"] = severity
    rows = await _db.code_diagnostics_rules.find(q, PROJ).limit(limit).to_list(limit)
    return {"diagnostics": rows, "total": await _db.code_diagnostics_rules.count_documents(q)}


# ─── Procgen Recipes ────────────────────────────────────────────────
@router.get("/procgen")
async def list_procgen(
    kind: Optional[str] = None,
    variant: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q: dict = {}
    if kind:    q["kind"] = kind
    if variant: q["variant"] = variant
    if tag:     q["tags"] = tag
    rows = await _db.procgen_recipes.find(q, PROJ).limit(limit).to_list(limit)
    return {"recipes": rows, "total": await _db.procgen_recipes.count_documents(q)}


# ─── Content Catalogues ─────────────────────────────────────────────
@router.get("/catalogues")
async def list_catalogues(
    category: Optional[str] = None,
    rarity: Optional[str] = None,
    era: Optional[str] = None,
    limit: int = Query(50, le=200),
    skip: int = Query(0, ge=0),
):
    q: dict = {}
    if category: q["category"] = category
    if rarity:   q["rarity"] = rarity
    if era:      q["era"] = era
    rows = await _db.content_catalogues.find(q, PROJ).skip(skip).limit(limit).to_list(limit)
    return {"items": rows, "total": await _db.content_catalogues.count_documents(q)}


# ─── Game Design Patterns ───────────────────────────────────────────
@router.get("/design")
async def list_design(
    pattern: Optional[str] = None,
    genre: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q: dict = {}
    if pattern: q["pattern"] = pattern
    if genre:   q["genre"] = genre
    rows = await _db.game_design_patterns.find(q, PROJ).limit(limit).to_list(limit)
    return {"patterns": rows, "total": await _db.game_design_patterns.count_documents(q)}


# ─── Balance Curves ─────────────────────────────────────────────────
@router.get("/balance-curves")
async def list_balance(
    curve: Optional[str] = None,
    use: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    q: dict = {}
    if curve: q["curve"] = curve
    if use:   q["use"] = use
    rows = await _db.game_balance_curves.find(q, PROJ).limit(limit).to_list(limit)
    return {"curves": rows, "total": await _db.game_balance_curves.count_documents(q)}


# ─── Engine API Schemas ─────────────────────────────────────────────
@router.get("/engines")
async def list_engines(
    engine: Optional[str] = None,
    language: Optional[str] = None,
):
    q: dict = {}
    if engine:   q["engine"] = {"$regex": engine, "$options": "i"}
    if language: q["language"] = {"$regex": language, "$options": "i"}
    rows = await _db.engine_api_schemas.find(q, PROJ).limit(50).to_list(50)
    return {"engines": rows, "total": await _db.engine_api_schemas.count_documents(q)}


# ─── Agent context bundle — single big RAG payload ──────────────────
@router.get("/agent-context")
async def agent_context(
    topic: str = Query(..., min_length=2),
    language: Optional[str] = None,
    engine: Optional[str] = None,
    genre: Optional[str] = None,
    limit_each: int = Query(8, le=20),
):
    """Returns a unified context bundle the Galaxy Studio agent stuffs into
    its system prompt. Aggregates the most-relevant rows from every collection.
    Hyphenated, underscored, or space-separated topics are tokenized so the
    agent can ask for things like 'boss-fight' or 'save_load' and still hit.
    """
    # Tokenize: split on hyphen/underscore/space, drop tokens < 3 chars
    import re as _re
    tokens = [t for t in _re.split(r"[-_\s]+", topic.strip()) if len(t) >= 3]
    if not tokens:
        tokens = [topic]
    # Build a single OR regex like (boss|fight)
    token_regex = "|".join(_re.escape(t) for t in tokens)
    regex = {"$regex": token_regex, "$options": "i"}
    lang_q   = {"$regex": f"^{language}$", "$options": "i"} if language else None
    engine_q = {"$regex": engine, "$options": "i"} if engine else None

    async def _take(coll, q):
        return await coll.find(q, PROJ).limit(limit_each).to_list(limit_each)

    patches   = await _take(_db.patch_notes,         {"$or": [{"game": regex}, {"tags": regex}, {"title": regex}, {"summary": regex}]})
    refs_q: dict = {"$or": [{"description": regex}, {"tags": regex}, {"topic": regex}]}
    if lang_q:   refs_q["primary_language"] = lang_q
    if engine_q: refs_q["engine"] = engine_q
    refs       = await _take(_db.github_code_refs, refs_q)
    tpl_q: dict = {"$or": [{"kind": regex}, {"tags": regex}, {"description": regex}]}
    if lang_q:   tpl_q["language"] = lang_q
    templates  = await _take(_db.code_synthesis_templates, tpl_q)
    diag_q: dict = {"$or": [{"rule": regex}, {"description": regex}, {"tags": regex}]}
    if lang_q:   diag_q["language"] = lang_q
    diagnostics= await _take(_db.code_diagnostics_rules, diag_q)
    recipes    = await _take(_db.procgen_recipes,  {"$or": [{"kind": regex}, {"tags": regex}, {"description": regex}]})
    catalogues = await _take(_db.content_catalogues, {"$or": [{"category": regex}, {"item": regex}, {"name": regex}, {"tags": regex}]})
    design_q: dict = {"$or": [{"pattern": regex}, {"description": regex}, {"tags": regex}]}
    if genre: design_q["genre"] = genre
    patterns   = await _take(_db.game_design_patterns, design_q)
    curves     = await _take(_db.game_balance_curves, {"$or": [{"curve": regex}, {"use": regex}, {"description": regex}]})
    eng_q: dict = {"$or": [{"engine": regex}, {"language": regex}, {"tags": regex}]}
    if engine_q: eng_q.setdefault("engine", engine_q)
    engines    = await _take(_db.engine_api_schemas, eng_q)

    # ─── NEW: include the 4 newer collections in the RAG bundle ───
    gs_q: dict = {"$or": [{"genre": regex}, {"kind": regex}, {"tags": regex}]}
    if engine_q: gs_q.setdefault("engine", engine_q)
    if genre:    gs_q["genre"] = genre
    gamestate  = await _take(_db.gamestate_schemas, gs_q)

    qa_q: dict = {"$or": [{"invariant_name": regex}, {"description": regex}, {"tags": regex}, {"fix_hint": regex}]}
    if genre:    qa_q["genre"] = genre
    oracles    = await _take(_db.qa_oracles, qa_q)

    ai_q: dict = {"$or": [{"strategy": regex}, {"domain": regex}, {"description": regex}, {"tags": regex}]}
    ai_weights = await _take(_db.ai_generative_weights, ai_q)

    br_q: dict = {"$or": [{"engine": regex}, {"platform": regex}, {"mode": regex}, {"description": regex}, {"tags": regex}]}
    if engine_q: br_q.setdefault("engine", engine_q)
    build_recipes = await _take(_db.build_recipes, br_q)

    # ─── Phase 4: similarity / theft / AST / stylometric / legal / academic / agnostic / training ───
    sim_q: dict = {"$or": [{"technique": regex}, {"description": regex}, {"tags": regex}]}
    if lang_q: sim_q["language"] = lang_q
    code_similarity = await _take(_db.code_similarity_logic, sim_q)

    theft_q: dict = {"$or": [{"signature": regex}, {"description": regex}, {"tags": regex}]}
    if engine_q: theft_q["engine"] = engine_q
    asset_theft = await _take(_db.asset_engine_theft, theft_q)

    ast_q: dict = {"$or": [{"detector": regex}, {"description": regex}, {"tags": regex}]}
    if lang_q: ast_q["language"] = lang_q
    ast_detection = await _take(_db.ast_detection, ast_q)

    sty_q: dict = {"$or": [{"feature": regex}, {"description": regex}, {"tags": regex}]}
    if lang_q: sty_q["language"] = lang_q
    stylometric = await _take(_db.stylometric_fingerprint, sty_q)

    legal_precedents = await _take(_db.mechanic_legal_paradox, {"$or": [{"case": regex}, {"facts": regex}, {"outcome": regex}, {"description": regex}]})
    academic = await _take(_db.academic_frameworks, {"$or": [{"name": regex}, {"description": regex}, {"tags": regex}]})
    agnostic_content = await _take(_db.agnostic_content_index, {"$or": [{"source": regex}, {"description": regex}, {"tags": regex}]})
    training = await _take(_db.training_recipes, {"$or": [{"recipe": regex}, {"description": regex}, {"tags": regex}]})
    clones = await _take(_db.game_playing_logic_clones, {"$or": [{"original": regex}, {"clone": regex}, {"legal_notes": regex}, {"tags": regex}]})
    linting = await _take(_db.linting_formatters, ({"language": lang_q} if lang_q else {}))

    return {
        "topic": topic,
        "tokens": tokens,
        "filters": {"language": language, "engine": engine, "genre": genre},
        "patches":           patches,
        "github_refs":       refs,
        "templates":         templates,
        "diagnostics":       diagnostics,
        "procgen":           recipes,
        "catalogues":        catalogues,
        "design":            patterns,
        "balance_curves":    curves,
        "engines":           engines,
        "gamestate_schemas": gamestate,
        "qa_oracles":        oracles,
        "ai_weights":        ai_weights,
        "build_recipes":     build_recipes,
        # ─── Phase 4 bundle ───
        "code_similarity":   code_similarity,
        "asset_theft":       asset_theft,
        "ast_detection":     ast_detection,
        "stylometric":       stylometric,
        "legal_precedents":  legal_precedents,
        "academic":          academic,
        "agnostic_content":  agnostic_content,
        "training_recipes":  training,
        "logic_clones":      clones,
        "linting":           linting,
        "total": sum(len(x) for x in [
            patches, refs, templates, diagnostics, recipes, catalogues,
            patterns, curves, engines, gamestate, oracles, ai_weights, build_recipes,
            code_similarity, asset_theft, ast_detection, stylometric,
            legal_precedents, academic, agnostic_content, training, clones, linting,
        ]),
    }


# ─── Patch Notes ──────────────────────────────────────────────────────
@router.get("/patch-notes")
async def list_patch_notes(
    game: Optional[str] = None,
    kind: Optional[str] = None,
    tag:  Optional[str] = None,
    engine: Optional[str] = None,
    limit: int = Query(50, le=200),
    skip:  int = Query(0, ge=0),
):
    q: dict = {}
    if game:   q["$or"] = [{"game": {"$regex": game, "$options": "i"}}, {"slug": game.lower()}]
    if kind:   q["kind"] = kind
    if tag:    q["tags"] = tag
    if engine: q["engines"] = engine
    cursor = _db.patch_notes.find(q, PROJ).sort("release_date", -1).skip(skip).limit(limit)
    notes = await cursor.to_list(length=limit)
    total = await _db.patch_notes.count_documents(q)
    return {"patches": notes, "total": total, "showing": len(notes), "skip": skip}


@router.get("/patch-notes/games")
async def list_patch_games():
    pipeline = [
        {"$group": {"_id": "$game", "patches": {"$sum": 1}, "tags": {"$addToSet": "$tags"}}},
        {"$sort": {"patches": -1}},
    ]
    rows = await _db.patch_notes.aggregate(pipeline).to_list(200)
    games = [{"game": r["_id"], "patches": r["patches"]} for r in rows]
    return {"games": games, "total": len(games)}


# ─── GitHub Code References ──────────────────────────────────────────
@router.get("/github-code")
async def list_github_code(
    language: Optional[str] = None,
    engine:   Optional[str] = None,
    topic:    Optional[str] = None,
    tag:      Optional[str] = None,
    limit: int = Query(50, le=200),
    skip:  int = Query(0, ge=0),
):
    q: dict = {}
    if language: q["primary_language"] = {"$regex": f"^{language}$", "$options": "i"}
    if engine:   q["engine"]          = {"$regex": engine, "$options": "i"}
    if topic:    q["topic"]           = topic
    if tag:      q["tags"]            = tag
    cursor = _db.github_code_refs.find(q, PROJ).skip(skip).limit(limit)
    refs = await cursor.to_list(length=limit)
    total = await _db.github_code_refs.count_documents(q)
    return {"refs": refs, "total": total, "showing": len(refs), "skip": skip}


@router.get("/github-code/topics")
async def list_github_topics():
    pipeline = [
        {"$group": {"_id": "$topic", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows = await _db.github_code_refs.aggregate(pipeline).to_list(50)
    return {"topics": [{"topic": r["_id"], "count": r["count"]} for r in rows]}


# ─── Combined search — used by Galaxy Studio agent RAG ───────────────
@router.get("/search")
async def rag_search(q: str = Query(..., min_length=2), limit: int = Query(20, le=50)):
    """Unified case-insensitive search across all knowledge collections.
    Returns a single ordered list the agent can stuff into its prompt window."""
    regex = {"$regex": q, "$options": "i"}
    patches = await _db.patch_notes.find(
        {"$or": [{"game": regex}, {"title": regex}, {"summary": regex}, {"tags": regex}]},
        PROJ,
    ).limit(limit).to_list(limit)
    refs = await _db.github_code_refs.find(
        {"$or": [{"repo": regex}, {"description": regex}, {"tags": regex}, {"topic": regex},
                 {"primary_language": regex}, {"engine": regex}]},
        PROJ,
    ).limit(limit).to_list(limit)
    langs = await _db.language_classes.find(
        {"$or": [{"name": regex}, {"description": regex}, {"paradigm": regex}, {"category": regex}]},
        {**PROJ, "chapters": 0},
    ).limit(limit).to_list(limit)
    return {
        "query": q,
        "patches": patches,
        "github_refs": refs,
        "languages": langs,
        "total": len(patches) + len(refs) + len(langs),
    }


# ─── Trigger a re-seed (idempotent, dev convenience) ─────────────────
@router.post("/reseed")
async def reseed_all():
    out = {}
    try:
        from seeds.patch_notes_seed import seed_patch_notes
        out["patch_notes"] = await seed_patch_notes(_db)
    except Exception as e:
        out["patch_notes_error"] = str(e)[:200]
    try:
        from seeds.github_code_seed import seed_github_code
        out["github_code"] = await seed_github_code(_db)
    except Exception as e:
        out["github_code_error"] = str(e)[:200]
    try:
        from seeds.language_classes_seed import seed_language_classes
        out["language_classes"] = await seed_language_classes(_db)
    except Exception as e:
        out["language_classes_error"] = str(e)[:200]
    return {"status": "ok", "results": out}



# ═══ Live Scrapers control surface (2026-05-15) ══════════════════════
from fastapi import Body  # noqa: E402


@router.get("/scrapers")
async def list_scrapers():
    """List every registered scraper job with current enabled / last-run state."""
    rows = await _db.scraper_jobs.find({}, PROJ).to_list(200)
    return {"total": len(rows), "scrapers": rows}


@router.post("/scrapers/{name}/enable")
async def enable_scraper(name: str, enabled: bool = Body(True, embed=True)):
    """Toggle a scraper on/off by name (e.g. 'unity-blog')."""
    r = await _db.scraper_jobs.update_one(
        {"name": name}, {"$set": {"enabled": bool(enabled)}}
    )
    return {"name": name, "enabled": bool(enabled), "matched": r.matched_count}


@router.post("/scrapers/run-now")
async def scrapers_run_now():
    """Fire every eligible enabled scraper once. Off-by-default for safety."""
    try:
        from services.live_scrapers import run_scrapers_once
        return await run_scrapers_once(_db)
    except Exception as e:
        return {"error": str(e)[:240]}


# ═══ Training-recipes shortcut endpoints (Cross-Entropy, LoRA, ICL log-probs) ═══
@router.get("/training/recipes")
async def training_recipes(kind: Optional[str] = None, limit: int = 50):
    """Convenience endpoint over the `training_recipes` collection.
    kind ∈ {'cross-entropy','preference','adapter','in-context'} returns the
    filtered subset. No kind = all 18 SOTA recipes."""
    q: dict = {}
    if kind:
        prefix_map = {
            "cross-entropy":   "cross-entropy",
            "preference":      r"^(DPO|ORPO|KTO|rejection-sampling)",
            "adapter":         r"^(LoRA|QLoRA|full-finetune|instruction-tune)",
            "in-context":      r"^in-context",
        }
        pat = prefix_map.get(kind)
        if pat:
            q["recipe"] = {"$regex": pat, "$options": "i"}
    rows = await _db.training_recipes.find(q, PROJ).limit(max(1, min(200, limit))).to_list(limit)
    return {"kind": kind, "total": len(rows), "recipes": rows}
