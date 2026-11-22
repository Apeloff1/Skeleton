"""
💎 QUALITY GATE — exquisite-only. Every build LLM call is held to a HARDCODED minimum
quality of 95/100 across ALL factors. We do not deliver below 95.

- PRE-call:  QUALITY_DIRECTIVE is injected into every forge so the model aims for top-1% output.
- POST-call: audit_quality() scores the output; if any factor or the overall < 95, the caller
  regenerates with the auditor's feedback until it clears the bar (or returns the best attempt,
  flagged). Quality is hardcoded — there is no lower threshold and it cannot be configured down.
"""
from __future__ import annotations

import asyncio
import math

from core.forge_quality_contract import MAX_ARTIFACT_CHARS, checked_json, review_scores, source_digest
from core.http_errors import redact_client_text

from routes.playable import PlayableModelFailure, _GAME_ENSEMBLE, _llm_in_thread
from fastapi import HTTPException

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


def _unqualified(detail: str, digest: str = "") -> dict:
    return {
        "score": 0, "overall": 0, "factors": {}, "feedback": detail,
        "simulation": None, "passed": False, "enforced": MIN_QUALITY,
        "audit_complete": False, "source_sha256": digest,
        "evidence_scope": "model-review-structural-proxy",
    }


async def audit_quality(kind: str, content: str, simulate: bool = False,
                        artifact: object = None) -> dict:
    """Review the exact bounded source, requiring all six independent factors.

    The compatibility artifact argument is not a second source of authority:
    the simulation always observes the candidate text actually sent to the
    model judge. Structural proxy metrics cannot certify native gameplay.
    """
    del artifact
    if (
        type(kind) is not str or not 1 <= len(kind) <= 128
        or type(content) is not str or not 0 < len(content) <= MAX_ARTIFACT_CHARS
    ):
        return _unqualified("Artifact or kind exceeds complete review budget")
    try:
        digest = source_digest(content)
    except UnicodeError:
        return _unqualified("Artifact contains invalid text")
    prompt = f"Artifact kind: {kind}\nArtifact JSON:\n{content}\n\nAudit it."
    try:
        routed = await asyncio.to_thread(_llm_in_thread, prompt, _AUDIT_SYS, _GAME_ENSEMBLE)
        overall, factors, feedback = review_scores(routed.get("content", ""), QUALITY_FACTORS)
    except (HTTPException, PlayableModelFailure):
        raise
    except Exception:
        return _unqualified("Complete quality judgment unavailable", digest)

    model_floor = min(overall, *factors.values())
    score = model_floor
    sim = None
    if simulate:
        try:
            from core.forge_validator import simulation_metrics, SIM_WEIGHT
            candidate = checked_json(content)
            if type(candidate) is not dict or not candidate:
                raise ValueError("simulation needs a structured candidate")
            sim = simulation_metrics(kind, candidate)
            raw = sim["sim_score"]
            if (
                type(raw) not in (int, float)
                or not 0 <= raw <= 100 or not math.isfinite(raw)
            ):
                raise ValueError("simulation score is invalid")
            sim_score = int(raw)
            factors = {**factors, "simulation": sim_score}
            blended = round((1 - SIM_WEIGHT) * model_floor + SIM_WEIGHT * sim_score)
            # A strong proxy cannot compensate for any failed model factor.
            # Simulation remains a hard gate for native-sensitive stages.
            score = min(model_floor, blended)
            if any(label in kind.lower() for label in (
                "physic", "tileset", "cinematic", "camera", "procedural"
            )):
                score = min(score, sim_score)
        except Exception:
            return {
                **_unqualified("Required structural simulation unavailable", digest),
                "overall": overall, "factors": factors,
            }

    return {
        "score": score, "overall": overall, "factors": factors,
        "feedback": redact_client_text(feedback, max_len=200),
        "simulation": sim, "passed": score >= MIN_QUALITY,
        "enforced": MIN_QUALITY, "audit_complete": True,
        "source_sha256": digest, "evidence_scope": "model-review-structural-proxy",
    }
