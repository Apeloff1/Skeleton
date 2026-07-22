"""
routes/hub_tools.py — CodeDock v9 "Ultimate Hub" sub-router.

Extracted from server.py (Feb 2026 Phase-6 decomposition). Bundles 18
endpoints across 7 closely-related Hub subsystems that were declared
inline in server.py:

  /api/v9/info               — build info + provider/registry totals
  /api/language-packs[/...]  — LANGUAGE_PACK_REGISTRY listing
  /api/expansions[/...]      — EXPANSION_PACKS CRUD-lite
  /api/ai/hub/*              — ai_hub-backed feature suggestion APIs
  /api/healing/*             — self_healer-backed diagnose/fix/organize
  /api/import/file           — import_export.import_file
  /api/export/file           — import_export.export_file
  /api/export/formats        — listing helper
  /api/algorithms[/...]      — ALGORITHM_REGISTRY listing

All module-level singletons (``ai_hub``, ``self_healer``, ``import_export``,
registries) live in server.py. We access them via a lazy ``_srv()``
accessor inside each handler so this sub-router never imports server.py
at load time (no circular).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["hub-tools"])


@router.get("/hub/expansions/installed")
async def list_installed_expansions():
    """Surface installed expansions (installed_expansions was written but never read)."""
    s = _srv()
    rows = await s.db.installed_expansions.find({}, {"_id": 0}).to_list(200)
    return {"expansions": rows, "count": len(rows)}


def _srv():
    """Lazy accessor for the server module that owns all Hub singletons."""
    import server as _s  # lazy — avoids circular import
    return _s


# ═══════════════════════════════════════════════════════════════════════
# v9 INFO
# ═══════════════════════════════════════════════════════════════════════

@router.get("/v9/info")
async def get_v9_info():
    """Get CodeDock v9.0.0 Ultimate Hub information."""
    s = _srv()
    return {
        "version":         "9.0.0",
        "codename":        "Ultimate Hub",
        "build":           "2026.02.22-ULTIMATE",
        "features": [
            "self_evolving_ai",
            "multi_llm_support",
            "50_plus_languages",
            "self_healing",
            "expansion_packs",
            "compilation_bible",
            "predictive_upgrades",
            "state_of_art_algorithms",
        ],
        "llm_providers":   list(s.ai_hub.providers.keys()),
        "language_packs":  len(s.LANGUAGE_PACK_REGISTRY),
        "expansion_packs": len(s.EXPANSION_PACKS),
        "algorithms":      sum(len(v) for v in s.ALGORITHM_REGISTRY.values()),
    }


# ═══════════════════════════════════════════════════════════════════════
# LANGUAGE PACKS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/language-packs")
async def get_language_packs():
    """Get all language packs."""
    registry = _srv().LANGUAGE_PACK_REGISTRY
    packs = [{"id": lang_id, **pack} for lang_id, pack in registry.items()]
    return {
        "packs":      packs,
        "total":      len(packs),
        "categories": list({p["category"] for p in registry.values()}),
    }


@router.get("/language-packs/{category}")
async def get_language_packs_by_category(category: str):
    """Get language packs by category."""
    registry = _srv().LANGUAGE_PACK_REGISTRY
    packs = [
        {"id": k, **v} for k, v in registry.items()
        if v.get("category") == category
    ]
    return {"category": category, "packs": packs, "count": len(packs)}


# ═══════════════════════════════════════════════════════════════════════
# EXPANSIONS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/expansions")
async def get_expansions():
    """Get all expansion packs."""
    s = _srv()
    return {
        "expansions": list(s.EXPANSION_PACKS.values()),
        "total":      len(s.EXPANSION_PACKS),
        "categories": [e.value for e in s.ExpansionCategory],
    }


@router.get("/expansions/{pack_id}")
async def get_expansion(pack_id: str):
    """Get specific expansion pack."""
    s = _srv()
    if pack_id in s.EXPANSION_PACKS:
        return s.EXPANSION_PACKS[pack_id]
    raise HTTPException(status_code=404, detail="Expansion not found")


@router.post("/expansions/{pack_id}/install")
async def install_expansion(pack_id: str):
    """Install an expansion pack."""
    s = _srv()
    if pack_id not in s.EXPANSION_PACKS:
        raise HTTPException(status_code=404, detail="Expansion not found")
    await s.db.installed_expansions.update_one(
        {"pack_id": pack_id},
        {"$set": {
            "pack_id":      pack_id,
            "installed_at": datetime.utcnow(),
            "status":       s.ExpansionStatus.INSTALLED.value,
        }},
        upsert=True,
    )
    return {"success": True, "pack_id": pack_id, "status": "installed"}


# ═══════════════════════════════════════════════════════════════════════
# AI HUB
# ═══════════════════════════════════════════════════════════════════════

@router.get("/ai/hub/providers")
async def get_llm_providers():
    """Get available LLM providers."""
    s = _srv()
    return {
        "providers": [
            {
                "id":        provider.value,
                "name":      provider.value.capitalize(),
                "model":     info["model"],
                "available": info["available"],
            }
            for provider, info in s.ai_hub.providers.items()
        ]
    }


@router.post("/ai/hub/suggest-features")
async def suggest_features(context: dict = {}):
    """AI-powered feature suggestions."""
    suggestions = await _srv().ai_hub.suggest_features(context)
    return {"suggestions": suggestions}


@router.post("/ai/hub/query-sota")
async def query_sota(data: dict):
    """Query state-of-the-art developments."""
    domain = data.get("domain", "compiler optimization")
    return await _srv().ai_hub.query_sota(domain)


@router.post("/ai/hub/auto-implement")
async def auto_implement(feature_spec: dict):
    """Generate implementation plan for a feature."""
    return await _srv().ai_hub.auto_implement_feature(feature_spec)


# ═══════════════════════════════════════════════════════════════════════
# HEALING
# ═══════════════════════════════════════════════════════════════════════

@router.post("/healing/diagnose")
async def diagnose_error(error: dict):
    """Diagnose an error."""
    return await _srv().self_healer.diagnose(error)


@router.post("/healing/auto-fix")
async def auto_fix_code(data: dict):
    """Attempt automatic fix."""
    return await _srv().self_healer.auto_fix(
        data.get("code", ""),
        data.get("error", {}),
    )


@router.post("/healing/organize")
async def organize_library(data: dict):
    """Self-organize library."""
    files = data.get("files", [])
    return await _srv().self_healer.organize_library(files)


# ═══════════════════════════════════════════════════════════════════════
# IMPORT / EXPORT
# ═══════════════════════════════════════════════════════════════════════

@router.post("/import/file")
async def import_file(data: dict):
    """Import a file."""
    return await _srv().import_export.import_file(
        data.get("content",  ""),
        data.get("filename", "untitled"),
        data.get("format"),
    )


@router.post("/export/file")
async def export_file(data: dict):
    """Export code in various formats."""
    return await _srv().import_export.export_file(
        data.get("code",     ""),
        data.get("language", "text"),
        data.get("format",   "txt"),
        data.get("options",  {}),
    )


@router.get("/export/formats")
async def get_export_formats():
    """Get supported export formats."""
    ie = _srv().import_export
    return {
        "import_formats": ie.SUPPORTED_IMPORT_FORMATS,
        "export_formats": ie.SUPPORTED_EXPORT_FORMATS,
    }


# ═══════════════════════════════════════════════════════════════════════
# ALGORITHMS
# ═══════════════════════════════════════════════════════════════════════

@router.get("/algorithms")
async def get_algorithms():
    """Get all algorithms."""
    registry = _srv().ALGORITHM_REGISTRY
    return {
        "algorithms": registry,
        "categories": list(registry.keys()),
    }


@router.get("/algorithms/{category}")
async def get_algorithms_by_category(category: str):
    """Get algorithms by category."""
    registry = _srv().ALGORITHM_REGISTRY
    if category in registry:
        return {"category": category, "algorithms": registry[category]}
    raise HTTPException(status_code=404, detail="Category not found")
