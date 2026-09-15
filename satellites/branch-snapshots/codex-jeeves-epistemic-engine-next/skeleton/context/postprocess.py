"""Context-step post-processing — runs after seal, outside snowball mass.

The ten conserved-mass stages stay 1.0. Post-process is a perpendicular
layer: codec the vision, pulse the galaxy, attach decoder reconstruction,
cite Hoag + any game pointer, keep stored_prose at 0.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def postprocess_context(ctx: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    vision = str(ctx.get("vision") or payload.get("era") or "")
    citation = ""
    url = ""
    ref = ctx.get("reference") or payload.get("reference")
    if isinstance(ref, dict):
        citation = str(ref.get("citation") or "")
        url = str(ref.get("url") or "")
        if not citation and payload.get("citation"):
            citation = str(payload.get("citation") or "")
    elif payload.get("citation"):
        citation = str(payload.get("citation") or "")

    from skeleton.galaxy.system import live_galaxy

    gxy = live_galaxy()
    card = gxy.pulse(vision, citation=citation, url=url, sleep=False)
    longform = gxy.ingest_turns(
        [vision, str(payload.get("era") or ""), str((payload.get("jeeves") or {}).get("next", {}).get("text") or "jeeves")],
        citation=citation,
    )
    payload["galaxy"] = {
        "route": card["route"],
        "memory_id": card["memory"]["id"],
        "compiled_id": card["compiled"]["id"],
        "index_id": card["index"]["id"],
        "principle": (card["principle"] or {}).get("id") if card.get("principle") else None,
        "decoded": card["decoded"]["reconstructed"],
        "atom_recall": card["decoded"]["atom_recall"],
        "longform": longform["structure"],
        "density": longform["density"],
        "hoag": card["hoag"],
        "wiki_topics": len(card["wiki"].get("topics") or {}),
        "stored_prose": 0,
    }
    payload["stored_prose"] = 0
    payload["postprocessed"] = True
    return payload


def attach_postprocess(execute_fn):
    """Decorator leftover for callers that wrap GameForgeRun.execute."""

    def wrapped(*args, **kwargs):
        payload = execute_fn(*args, **kwargs)
        ctx = kwargs
        return postprocess_context(ctx, payload)

    return wrapped
