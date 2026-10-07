"""
═══════════════════════════════════════════════════════════════════════════
 Agent Knowledge RAG Helper
─────────────────────────────────────────────────────────────────────────
 Retrieves SOTA knowledge from the local Mongo DBs (patch_notes, github_code
 refs, code synthesis templates, diagnostics rules, procgen recipes, content
 catalogues, game design patterns, balance curves, engine API schemas) and
 formats it as a compact context block any agent can stuff into its system
 prompt. Pure local lookups — works fully offline.

 Usage from any agent:

     from services.agent_knowledge_rag import build_rag_context

     ctx = await build_rag_context(topic="boss-fight", language="C#", engine="Unity")
     system_prompt = ctx + "\\n\\n" + base_system_prompt
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import logging
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / '.env')

log = logging.getLogger("agent.knowledge.rag")

_client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
_db = _client[os.environ.get("DB_NAME", "codedock")]


def _section(title: str, rows: list[dict], fmt) -> str:
    if not rows:
        return ""
    lines = [f"### {title}"]
    for r in rows:
        try:
            lines.append("• " + fmt(r))
        except Exception:
            continue
    return "\n".join(lines) + "\n"


async def build_rag_context(
    topic: str,
    language: Optional[str] = None,
    engine: Optional[str] = None,
    genre: Optional[str] = None,
    take: int = 5,
) -> str:
    """Returns a compact markdown context string for the agent's system prompt."""
    try:
        regex = {"$regex": topic, "$options": "i"}
        lang_q = {"$regex": f"^{language}$", "$options": "i"} if language else None
        engine_q = {"$regex": engine, "$options": "i"} if engine else None

        async def _take(coll, q):
            return await coll.find(q, {"_id": 0}).limit(take).to_list(take)

        # Engine schema (most useful first)
        eng_q: dict = {}
        if engine_q: eng_q["engine"] = engine_q
        engines = await _take(_db.engine_api_schemas, eng_q)

        # Code patterns / templates
        tpl_q: dict = {"$or": [{"kind": regex}, {"tags": regex}, {"description": regex}]}
        if lang_q: tpl_q["language"] = lang_q
        templates = await _take(_db.code_synthesis_templates, tpl_q)

        # GitHub canonical refs
        ref_q: dict = {"$or": [{"description": regex}, {"tags": regex}, {"topic": regex}]}
        if lang_q: ref_q["primary_language"] = lang_q
        if engine_q: ref_q["engine"] = engine_q
        refs = await _take(_db.github_code_refs, ref_q)

        # Diagnostics for the chosen language
        diag_q: dict = {}
        if lang_q: diag_q["language"] = lang_q
        diagnostics = await _take(_db.code_diagnostics_rules, diag_q)

        # Patch notes — what the meta has been doing lately for this kind of game
        patch_q: dict = {"$or": [{"game": regex}, {"tags": regex}, {"summary": regex}]}
        if genre: patch_q["tags"] = genre
        patches = await _take(_db.patch_notes, patch_q)

        # Design patterns
        design_q: dict = {"$or": [{"pattern": regex}, {"description": regex}, {"tags": regex}]}
        if genre: design_q["genre"] = genre
        patterns = await _take(_db.game_design_patterns, design_q)

        # Balance curves
        curves = await _take(_db.game_balance_curves, {"$or": [{"curve": regex}, {"use": regex}]})

        # Procgen recipes
        recipes = await _take(_db.procgen_recipes, {"$or": [{"kind": regex}, {"tags": regex}, {"description": regex}]})

        # Content catalogues — sample
        cat_q: dict = {"$or": [{"category": regex}, {"item": regex}]}
        catalogues = await _take(_db.content_catalogues, cat_q)

        # NEW: gamestate, qa, ai-weights, build-recipes
        gs_q: dict = {"$or": [{"genre": regex}, {"kind": regex}, {"tags": regex}]}
        if engine_q: gs_q.setdefault("engine", engine_q)
        if genre:    gs_q["genre"] = genre
        gamestate = await _take(_db.gamestate_schemas, gs_q)

        qa_q: dict = {"$or": [{"invariant_name": regex}, {"description": regex}, {"tags": regex}]}
        if genre: qa_q["genre"] = genre
        oracles = await _take(_db.qa_oracles, qa_q)

        ai_q: dict = {"$or": [{"strategy": regex}, {"domain": regex}, {"description": regex}, {"tags": regex}]}
        ai_weights = await _take(_db.ai_generative_weights, ai_q)

        br_q: dict = {"$or": [{"engine": regex}, {"platform": regex}, {"description": regex}, {"tags": regex}]}
        if engine_q: br_q.setdefault("engine", engine_q)
        build_recipes = await _take(_db.build_recipes, br_q)

        # ─── Phase 4: similarity / theft / legal / stylometric / training ──
        sim_q: dict = {"$or": [{"technique": regex}, {"description": regex}, {"tags": regex}]}
        if lang_q: sim_q["language"] = lang_q
        sim = await _take(_db.code_similarity_logic, sim_q)

        theft_q: dict = {"$or": [{"signature": regex}, {"description": regex}, {"tags": regex}]}
        if engine_q: theft_q["engine"] = engine_q
        theft = await _take(_db.asset_engine_theft, theft_q)

        ast_q: dict = {"$or": [{"detector": regex}, {"description": regex}, {"tags": regex}]}
        if lang_q: ast_q["language"] = lang_q
        ast = await _take(_db.ast_detection, ast_q)

        sty_q: dict = {"$or": [{"feature": regex}, {"description": regex}, {"tags": regex}]}
        if lang_q: sty_q["language"] = lang_q
        sty = await _take(_db.stylometric_fingerprint, sty_q)

        legal = await _take(
            _db.mechanic_legal_paradox,
            {"$or": [{"case": regex}, {"facts": regex}, {"outcome": regex}, {"description": regex}]},
        )
        academic = await _take(
            _db.academic_frameworks,
            {"$or": [{"name": regex}, {"description": regex}, {"tags": regex}]},
        )
        agnostic = await _take(
            _db.agnostic_content_index,
            {"$or": [{"source": regex}, {"description": regex}, {"tags": regex}]},
        )
        training = await _take(
            _db.training_recipes,
            {"$or": [{"recipe": regex}, {"description": regex}, {"tags": regex}]},
        )

        sections = [
            f"## 🧠 GROUNDED CONTEXT (topic={topic!r}, lang={language!r}, engine={engine!r}, genre={genre!r})\n",
            _section("Engine API", engines,
                     lambda r: f"{r.get('engine')} {r.get('version','')} — lifecycle: {', '.join(r.get('lifecycle', [])[:6])} — bootstrap: {r.get('bootstrap','')[:140]}"),
            _section("Game-State Schemas", gamestate,
                     lambda r: f"{r.get('engine')}/{r.get('genre')}/{r.get('kind')} — wire={r.get('wire',{}).get('ext')} migration={r.get('migration_hint','')[:120]}"),
            _section("Code Templates", templates,
                     lambda r: f"[{r.get('kind')}/{r.get('language')}] {r.get('description','')} :: {r.get('body','')[:160]}"),
            _section("Canonical GitHub Refs", refs,
                     lambda r: f"{r.get('repo')} ({r.get('license')}) — {r.get('description','')[:140]} → {r.get('source_url','')}"),
            _section("Diagnostics to Avoid", diagnostics,
                     lambda r: f"[{r.get('severity')}] {r.get('rule')} ({r.get('language')}): {r.get('description','')} — fix: {r.get('fix_hint','')}"),
            _section("QA Oracles", oracles,
                     lambda r: f"[{r.get('severity')}] {r.get('invariant_name')} ({r.get('genre')}, {r.get('kind')}): assert {r.get('assertion','')} | fix: {r.get('fix_hint','')}"),
            _section("AI Generative Weight Recipes", ai_weights,
                     lambda r: f"{r.get('strategy')}/{r.get('domain')} @ {r.get('difficulty')} params={r.get('params')}"),
            _section("Recent Patch-Notes Meta", patches,
                     lambda r: f"{r.get('game')} {r.get('version','')} ({r.get('release_date','')}): {r.get('summary','')[:200]}"),
            _section("Design Patterns", patterns,
                     lambda r: f"{r.get('pattern')} ({r.get('genre')}): {r.get('description','')}"),
            _section("Balance Curves", curves,
                     lambda r: f"{r.get('curve')} for {r.get('use')}: {r.get('formula')} params={r.get('default_params')}"),
            _section("Procgen Recipes", recipes,
                     lambda r: f"{r.get('kind')}/{r.get('variant')}: {r.get('description','')}"),
            _section("Content Sample", catalogues,
                     lambda r: f"{r.get('rarity')} {r.get('era')} {r.get('category')}/{r.get('item')} — pow {r.get('stats',{}).get('power')}"),
            _section("Build / Packaging Recipes", build_recipes,
                     lambda r: f"{r.get('engine')} → {r.get('platform')} ({r.get('mode')}): compile=`{r.get('compile','')[:90]}` package=`{r.get('package','')[:60]}`"),
            _section("Code Similarity Detection", sim,
                     lambda r: f"{r.get('technique')} ({r.get('language')}): {r.get('description','')[:140]} thresholds={r.get('thresholds')}"),
            _section("Asset / Engine Theft Signatures", theft,
                     lambda r: f"[{r.get('severity')}] {r.get('signature')} ({r.get('engine')}): {r.get('description','')[:140]}"),
            _section("AST Detection", ast,
                     lambda r: f"{r.get('detector')} ({r.get('language')}): {r.get('description','')[:140]}"),
            _section("Stylometric Fingerprint Features", sty,
                     lambda r: f"{r.get('feature')} ({r.get('language')}): {r.get('description','')[:120]}"),
            _section("Legal Precedents (mechanic/expression)", legal,
                     lambda r: f"{r.get('case')} ({r.get('year')}): {r.get('facts','')[:80]} → {r.get('outcome','')[:120]}"),
            _section("Academic Frameworks", academic,
                     lambda r: f"{r.get('name')} ({r.get('author')}): {r.get('description','')[:140]}"),
            _section("License-Clean Content Sources", agnostic,
                     lambda r: f"{r.get('source')} [{r.get('license')}]: {r.get('description','')[:140]}"),
            _section("Training Recipes (loss / FT / log-probs)", training,
                     lambda r: f"{r.get('recipe')}: {r.get('description','')[:160]}"),
        ]
        body = "\n".join(s for s in sections if s)
        # Hard-cap so we don't blow the prompt window
        return body[:14000]
    except Exception as e:
        log.warning(f"build_rag_context failed: {e}")
        return ""
