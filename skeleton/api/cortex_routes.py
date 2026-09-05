"""Cortex API routes — HTTP surface for all operator commands.

Wires the command deck into FastAPI-style route handlers.
Each route returns a JSON dict with a `kind` discriminator.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from skeleton.cortex.deck import CommandDeck


deck: Optional[CommandDeck] = None


def _deck(root=None) -> CommandDeck:
    global deck
    if deck is None:
        deck = CommandDeck(root=root)
    return deck


# ── Policy routes ─────────────────────────────────────────

def get_policy_state(root=None) -> Dict[str, Any]:
    return _deck(root).policy_state()


def post_policy_gate(surface: str, score: float, root=None) -> Dict[str, Any]:
    return _deck(root).policy_gate(surface, score)


def post_policy_save(comment: str = "", author: str = "api", root=None) -> Dict[str, Any]:
    vid = _deck(root).save_policy_version(comment=comment, author=author)
    return {"kind": "policy-save-result", "version_id": vid, "stored_prose": 0}


def post_policy_rollback(version_id: str, root=None) -> Dict[str, Any]:
    return _deck(root).rollback_policy(version_id)


def post_policy_rollback_surface(surface: str, root=None) -> Dict[str, Any]:
    return _deck(root).rollback_policy_surface(surface)


def get_policy_versions(limit: int = 8, root=None) -> Dict[str, Any]:
    return _deck(root).policy_versions(limit=limit)


def get_policy_diff(a: str, b: str, root=None) -> Dict[str, Any]:
    return _deck(root).policy_diff(a, b)


def get_policy_lineage(version_id: str, root=None) -> Dict[str, Any]:
    return {"kind": "policy-lineage", "lineage": _deck(root).policy_lineage(version_id), "stored_prose": 0}


def get_rollback_preview(version_id: str, root=None) -> Dict[str, Any]:
    return _deck(root).rollback_preview(version_id)


# ── Verification routes ─────────────────────────────────

def post_verify_forge(files: Dict[str, str], request: str = "", root=None) -> Dict[str, Any]:
    return _deck(root).verify_forge(files, request=request)


def post_verify_plan(plan: Dict[str, Any], root=None) -> Dict[str, Any]:
    return _deck(root).verify_plan(plan)


def post_verify_pipeline(tree: Dict[str, Any], root=None) -> Dict[str, Any]:
    return _deck(root).verify_pipeline(tree)


def post_verify_npc(spec: Dict[str, Any], root=None) -> Dict[str, Any]:
    return _deck(root).verify_npc(spec)


def post_verify_dialogue(script: Dict[str, Any], root=None) -> Dict[str, Any]:
    return _deck(root).verify_dialogue(script)


# ── Repair routes ───────────────────────────────────────

def post_repair_orchestrate(surface: str, target_id: str, max_passes: int = 3, root=None) -> Dict[str, Any]:
    return _deck(root).repair_orchestrate(surface, target_id, max_passes=max_passes)


def get_repair_sessions(surface: str = "", root=None) -> Dict[str, Any]:
    return _deck(root).repair_sessions(surface)


def get_repair_effectiveness(surface: str = "", root=None) -> Dict[str, Any]:
    return _deck(root).repair_effectiveness(surface)


def get_repair_telemetry(surface: str = "", root=None) -> Dict[str, Any]:
    return _deck(root).repair_telemetry(surface)


def get_repair_errors(surface: str = "", root=None) -> Dict[str, Any]:
    return _deck(root).repair_errors(surface)


def get_repair_learned(root=None) -> Dict[str, Any]:
    return _deck(root).repair_learned()


def get_repair_strategy(surface: str, reason: str, root=None) -> Dict[str, Any]:
    return _deck(root).repair_strategy(surface, reason)


# ── Advanced subsystem routes ─────────────────────────────

def get_lattice_hud(root=None) -> Dict[str, Any]:
    return _deck(root).lattice_hud()


def get_lattice_editor(root=None) -> Dict[str, Any]:
    return _deck(root).lattice_editor()


def post_steering_register(name: str, strength: float = 1.0, root=None) -> Dict[str, Any]:
    return _deck(root).steering_register(name, strength=strength)


def post_steering_activate(name: str, weight: float = 1.0, root=None) -> Dict[str, Any]:
    _deck(root).steering_activate(name, weight)
    return {"kind": "steering-activate", "name": name, "weight": weight, "stored_prose": 0}


def post_steering_deactivate(name: str, root=None) -> Dict[str, Any]:
    _deck(root).steering_deactivate(name)
    return {"kind": "steering-deactivate", "name": name, "stored_prose": 0}


def get_steering_composite(root=None) -> Dict[str, Any]:
    return _deck(root).steering_composite()


def get_kv_cache(root=None) -> Dict[str, Any]:
    return _deck(root).kv_cache_stats()


def post_mouth_feed(phoneme: str, ts_ms: float, confidence: float = 1.0, root=None) -> Dict[str, Any]:
    return _deck(root).mouth_feed(phoneme, ts_ms, confidence)


def get_mouth_current(root=None) -> Dict[str, Any]:
    return _deck(root).mouth_current()


def get_lora(root=None) -> Dict[str, Any]:
    return _deck(root).lora_card()


def get_decoder(root=None) -> Dict[str, Any]:
    return _deck(root).decoder_card()


# ── Master route ──────────────────────────────────────────

def get_master_card(root=None) -> Dict[str, Any]:
    return _deck(root).master_card()
