"""
Orchestrate Skeleton GameForge 7-step conductor — vision, snowball, prototype, mass forge, world, cockpit, export. Bind era_bind citations, clipped mass, emit packs.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

STEPS = ["vision", "snowball", "prototype", "mass_forge", "world", "cockpit", "export"]


def process(data: dict) -> dict:
    refused = admit("gameforge_workflow", data)
    if refused:
        return refused
    step = data.get("step")
    if step is None:
        return stamp("gameforge_workflow", data, {"steps": STEPS})
    if step not in STEPS:
        return {
            "ok": False,
            "error": "unknown step",
            "card": "gameforge_workflow",
            "steps": list(STEPS),
        }
    index = STEPS.index(step)
    return stamp(
        "gameforge_workflow",
        data,
        {
            "steps": STEPS,
            "step": step,
            "index": index,
            "next": STEPS[(index + 1) % len(STEPS)],
        },
    )
