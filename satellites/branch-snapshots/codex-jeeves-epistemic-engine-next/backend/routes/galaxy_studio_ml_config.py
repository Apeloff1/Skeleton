"""
routes/galaxy_studio_ml_config.py — ML-config sub-router.

Extracted from routes/galaxy_studio.py (Phase-4 decomposition, Feb 2026).
Hosts the Cross-Entropy / Fine-Tune / In-Context-Learning dial-panel
endpoints + JSON-Schema export used by the frontend matrix UI. Reads &
mutates ``galaxy_builds.ml_config`` in core_db. No in-memory build state.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["galaxy-studio"])


@router.get("/build/{build_id}/ml-config")
async def get_ml_config(build_id: str):
    """Return the persisted Advanced ML config + relevant matrix dials for a build.
    Surfaces Cross-Entropy customization, Fine-Tuning execution, In-Context Learning Log-Probs,
    Self-Consistency and MCTS depths. Read-only inspection endpoint."""
    try:
        from services.database import db as _db
        b = await _db.galaxy_builds.find_one({"build_id": build_id}, {"_id": 0})
        if not b:
            return {"error": "build_not_found", "build_id": build_id}
        agent_mtx = b.get("agent_matrix") or {}
        ml_cfg    = b.get("ml_config")    or {}
        ce_dials  = {k: agent_mtx[k] for k in ("loss_ce", "loss_label_smooth", "loss_focal", "loss_mask") if k in agent_mtx}
        ft_dials  = {k: agent_mtx[k] for k in ("pref_dpo", "pref_orpo", "pref_kto", "lora_r", "qlora_4bit") if k in agent_mtx}
        icl_dials = {k: agent_mtx[k] for k in ("icl_logprobs", "icl_self_consistency", "icl_mcts") if k in agent_mtx}
        rag_dials = {k: agent_mtx[k] for k in agent_mtx.keys() if str(k).startswith("rag_")}
        return {
            "build_id":            build_id,
            "ml_config":           ml_cfg,
            "cross_entropy_dials": ce_dials,
            "fine_tuning_dials":   ft_dials,
            "in_context_dials":    icl_dials,
            "rag_dials":           rag_dials,
            "matrix_dial_count":   b.get("matrix_dial_count", 0),
            "matrix_keys":         b.get("matrix_keys", []),
        }
    except Exception as e:
        return {"error": str(e)[:200], "build_id": build_id}


@router.post("/build/{build_id}/ml-config")
async def update_ml_config(build_id: str, patch: dict):
    """Mutate the ml_config block on an existing build at runtime.

    Per-key ranged validation (2026-05-15) — see ``/ml-config/schema`` for
    the machine-readable version that the UI sliders read directly.
    Rejected keys / out-of-range values are collected into ``rejected``.
    """
    _PREF_TUNE_VOCAB = {"DPO", "ORPO", "KTO", "SimPO", "IPO"}
    _FT_MODES        = {"sft", "dpo", "orpo", "kto", "simpo", "ipo", "lora", "qlora", "full"}
    _LOSS_TYPES      = {"ce", "focal", "label_smooth", "mask", "dpo", "orpo", "kto", "simpo"}
    _LORA_R_DISCRETE = {4, 8, 16, 32, 64, 128, 256}

    def _is_num(x):  # accepts int OR float (but rejects bool which is int subclass)
        return isinstance(x, (int, float)) and not isinstance(x, bool)

    def _coerce_int_in(lo, hi):
        def f(v):
            if not _is_num(v): return None, "must_be_number"
            iv = int(v)
            if iv < lo or iv > hi: return None, f"out_of_range_{lo}_to_{hi}"
            return iv, None
        return f

    def _coerce_float_in(lo, hi):
        def f(v):
            if not _is_num(v): return None, "must_be_number"
            fv = float(v)
            if fv < lo or fv > hi: return None, f"out_of_range_{lo}_to_{hi}"
            return round(fv, 4), None
        return f

    def _coerce_bool(v):
        if isinstance(v, bool): return v, None
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return bool(v), None
        if isinstance(v, str) and v.lower() in ("true", "false", "yes", "no", "1", "0"):
            return v.lower() in ("true", "yes", "1"), None
        return None, "must_be_bool"

    def _coerce_enum(vocab, case_sensitive=True):
        def f(v):
            if not isinstance(v, str): return None, "must_be_string"
            check = v if case_sensitive else v.lower()
            if check not in vocab: return None, f"must_be_one_of_{sorted(vocab)}"
            return v, None
        return f

    def _coerce_int_set(allowed_set):
        def f(v):
            if not _is_num(v): return None, "must_be_number"
            iv = int(v)
            if iv not in allowed_set: return None, f"must_be_one_of_{sorted(allowed_set)}"
            return iv, None
        return f

    def _coerce_pref_list(v):
        if not isinstance(v, list): return None, "must_be_list"
        out: list[str] = []
        for item in v[:8]:
            if isinstance(item, str) and item in _PREF_TUNE_VOCAB:
                if item not in out: out.append(item)
            else:
                return None, f"items_must_be_in_{sorted(_PREF_TUNE_VOCAB)}"
        return out, None

    _SCHEMA = {
        "ce_loss_weight":      _coerce_int_in(0, 20),
        "ce_temperature":      _coerce_float_in(0.0, 2.0),
        "label_smoothing":     _coerce_float_in(0.0, 0.3),
        "focal_gamma":         _coerce_float_in(0.0, 5.0),
        "preference_finetune": _coerce_pref_list,
        "lora_r":              _coerce_int_set(_LORA_R_DISCRETE),
        "qlora_4bit":          _coerce_bool,
        "icl_logprobs_depth":  _coerce_int_in(0, 10),
        "icl_samples":         _coerce_int_in(1, 64),
        "self_consistency_k":  _coerce_int_in(1, 32),
        "mcts_depth":          _coerce_int_in(1, 20),
        "fine_tune_mode":      _coerce_enum(_FT_MODES,   case_sensitive=False),
        "loss_type":           _coerce_enum(_LOSS_TYPES, case_sensitive=False),
    }

    if not isinstance(patch, dict):
        return {"error": "patch_must_be_dict", "build_id": build_id}

    clean:    dict = {}
    rejected: dict = {}
    for k, v in patch.items():
        if k not in _SCHEMA:
            rejected[k] = "unknown_key"
            continue
        coerced, err = _SCHEMA[k](v)
        if err:
            rejected[k] = f"{err}_(received={v!r})"
        else:
            clean[k] = coerced

    if not clean:
        return {
            "error": "no_valid_keys",
            "build_id":     build_id,
            "rejected":     rejected,
            "allowed_keys": sorted(_SCHEMA.keys()),
        }
    try:
        from services.database import db as _db
        update_doc = {f"ml_config.{k}": v for k, v in clean.items()}
        res = await _db.galaxy_builds.update_one(
            {"build_id": build_id},
            {"$set": update_doc, "$currentDate": {"ml_config_updated_at": True}},
        )
        if res.matched_count == 0:
            return {"error": "build_not_found", "build_id": build_id, "rejected": rejected}
        b = await _db.galaxy_builds.find_one({"build_id": build_id}, {"_id": 0, "ml_config": 1})
        return {
            "build_id":  build_id,
            "updated":   clean,
            "rejected":  rejected,
            "ml_config": (b or {}).get("ml_config", {}),
        }
    except Exception as e:
        return {"error": str(e)[:200], "build_id": build_id}


@router.get("/ml-config/schema")
async def ml_config_schema():
    """Return the validation schema for ml_config so clients (UI sliders) can render
    correct ranges/enums without hardcoding. Mirror of the validator in update_ml_config."""
    return {
        "ce_loss_weight":      {"type": "int",        "min": 0,   "max": 20},
        "ce_temperature":      {"type": "float",      "min": 0.0, "max": 2.0},
        "label_smoothing":     {"type": "float",      "min": 0.0, "max": 0.3},
        "focal_gamma":         {"type": "float",      "min": 0.0, "max": 5.0},
        "preference_finetune": {"type": "list[str]",  "vocab":   ["DPO", "ORPO", "KTO", "SimPO", "IPO"]},
        "lora_r":              {"type": "int_set",    "values":  [4, 8, 16, 32, 64, 128, 256]},
        "qlora_4bit":          {"type": "bool"},
        "icl_logprobs_depth":  {"type": "int",        "min": 0,   "max": 10},
        "icl_samples":         {"type": "int",        "min": 1,   "max": 64},
        "self_consistency_k":  {"type": "int",        "min": 1,   "max": 32},
        "mcts_depth":          {"type": "int",        "min": 1,   "max": 20},
        "fine_tune_mode":      {"type": "enum",       "vocab":   ["sft", "dpo", "orpo", "kto", "simpo", "ipo", "lora", "qlora", "full"]},
        "loss_type":           {"type": "enum",       "vocab":   ["ce", "focal", "label_smooth", "mask", "dpo", "orpo", "kto", "simpo"]},
    }


@router.get("/build/{build_id}/prompt-preview")
async def preview_build_prompt(build_id: str):
    """Show what an LLM-agent would see for a given build: the ML directives block
    + matrix highlights block that get prepended to every system_prompt. This is
    how the user's matrix dials and ml_config actually influence content output."""
    try:
        from services.game_llm_service import (
            load_build_context, _format_ml_directives, _format_matrix_highlights,
        )
        ctx = await load_build_context(build_id)
        if not ctx:
            return {"error": "build_not_found", "build_id": build_id}
        ml_block  = _format_ml_directives(ctx.get("ml_config")) or ""
        mtx_block = _format_matrix_highlights(ctx.get("matrices")) or ""
        return {
            "build_id":                build_id,
            "ml_directives_block":     ml_block,
            "matrix_highlights_block": mtx_block,
            "ml_directives_chars":     len(ml_block),
            "matrix_highlights_chars": len(mtx_block),
            "matrix_keys_active":      sorted((ctx.get("matrices")  or {}).keys()),
            "ml_config_keys":          sorted((ctx.get("ml_config") or {}).keys()),
        }
    except Exception as e:
        return {"error": str(e)[:200], "build_id": build_id}
