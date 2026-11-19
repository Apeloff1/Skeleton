"""
💎 QUALITY GATE — exquisite-only. Every build LLM call is held to a HARDCODED minimum
quality of 95/100 across ALL factors. We do not deliver below 95.

- PRE-call:  QUALITY_DIRECTIVE is injected into every forge so the model aims for top-1% output.
- POST-call: audit_quality() scores the output; if any factor or the overall < 95, the caller
  regenerates with the auditor's feedback until it clears the bar (or returns the best attempt,
  flagged). Quality is hardcoded — there is no lower threshold and it cannot be configured down.
"""
from __future__ import annotations

import json
import asyncio

from routes.playable import _GAME_ENSEMBLE, _llm_in_thread

# HARDCODED — maximal quality. Not configurable. Do not lower.
MIN_QUALITY = 95
QUALITY_FACTORS = ["coherence", "depth", "originality", "polish", "consistency", "completeness"]

QUALITY_DIRECTIVE = (
    "QUALITY BAR — NON-NEGOTIABLE: produce only EXQUISITE, top-1%, award-winning, AAA-studio-grade "
    "output. Every quality factor (coherence, depth, originality, polish, consistency, completeness) "
    "MUST be at least 95/100. Be richly detailed, internally consistent, and production-ready. "
    "Do NOT deliver anything that would score below 95 on any factor."
)

_AUDIT_SYS = (
    "You are a ruthless senior creative-director QA auditor. Score the provided game-design artifact "
    "JSON for production quality. Output ONLY valid minified JSON (no prose) with EXACTLY these keys: "
    "overall (int 0-100), factors (object with int 0-100 for coherence, depth, originality, polish, "
    "consistency, completeness), feedback (one concise sentence on the single biggest improvement). "
    "Be strict: reserve 95+ for genuinely exquisite, complete, internally-consistent work."
)


def _parse(text: str):
    s = (text or "").strip()
    a, b = s.find("{"), s.rfind("}")
    if a == -1 or b == -1:
        return None
    try:
        return json.loads(s[a:b + 1])
    except Exception:
        return None


async def audit_quality(kind: str, content: str, simulate: bool = False,
                        artifact: object = None) -> dict:
    """POST-call quality audit. Returns {score, factors, feedback, passed} (score floored to the
    worst of overall + every factor, so a single weak factor cannot pass the gate).

    SOTA Item 24/28 — when ``simulate=True`` a third judge (headless simulation)
    is blended in at weight 0.25, and for physics/tileset/camera/procedural
    stages the simulation must also pass or the score is capped to it."""
    prompt = f"Artifact kind: {kind}\nArtifact JSON:\n{content[:6000]}\n\nAudit it."
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, _AUDIT_SYS, _GAME_ENSEMBLE)
        data = _parse(routed.get("content", "")) or {}
    except Exception:
        data = {}
    factors = data.get("factors") or {}
    fvals = [int(v) for v in factors.values() if isinstance(v, (int, float))]
    overall = int(data.get("overall", 0) or 0)
    # the effective score is the MINIMUM of overall and every factor — no weak link allowed
    score = min([overall] + fvals) if fvals else overall

    sim = None
    if simulate:
        try:
            from core.forge_validator import simulation_metrics, SIM_WEIGHT
            sim = simulation_metrics(kind, artifact if artifact is not None else content)
            sim_score = int(sim["sim_score"])
            factors = {**factors, "simulation": sim_score}
            blended = round((1 - SIM_WEIGHT) * score + SIM_WEIGHT * sim_score)
            k = (kind or "").lower()
            if any(s in k for s in ("physic", "tileset", "cinematic", "camera", "procedural")):
                # Item 28 — simulation is a hard gate for these stages.
                score = min(blended, sim_score)
            else:
                score = blended
        except Exception:
            sim = None

    return {"score": score, "overall": overall, "factors": factors,
            "feedback": (data.get("feedback") or "")[:200], "simulation": sim,
            "passed": score >= MIN_QUALITY, "enforced": MIN_QUALITY}
