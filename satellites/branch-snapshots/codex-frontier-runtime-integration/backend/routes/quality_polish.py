"""
✨ POLISH LOOP — targeted re-write passes that iterate a forge artifact until it
clears the 95 quality gate (quality-gate CHURN, follow-up to the auto-improve summary loop).

Why this exists
---------------
Forge audit scores were consistently landing BELOW the 95 gate (narrative ~48,
physics ~58, tileset ~47, camera…) even though ``_llm_json`` retries up to 4x and
returns the highest-scoring attempt. Two root causes, both addressed here:

1. The gate FLOORS the score to the minimum of overall + every factor, and the
   single auditor is strict — one weak sub-score caps the whole artifact.
2. Retries re-roll from scratch; nothing *targets* the auditor's own feedback.

The polish pass keeps the best attempt, feeds the auditor's feedback back into a
targeted REWRITE (not a fresh roll), and re-audits each pass — iterating until
``MIN_QUALITY`` is cleared or ``MAX_POLISH_PASSES`` is exhausted. It always
returns the highest-scoring artifact seen, plus a full per-pass trail so the
improvement is inspectable instead of a black box.
"""
from __future__ import annotations

import json
import asyncio

from routes.quality import audit_quality, MIN_QUALITY, QUALITY_FACTORS
from routes.playable import _GAME_ENSEMBLE, _llm_in_thread

# Tuned for the gate: polish passes are cheap relative to full forge re-rolls.
MAX_POLISH_PASSES = 5
# If a pass fails to improve on the best score this many times in a row, stop —
# further passes have plateaued and only burn budget.
PLATEAU_TOLERANCE = 2

_POLISH_SYS = (
    "You are a world-class game-design editor doing a TARGETED polish pass on an "
    "artifact that failed a {gate}/100 quality gate. You are given the artifact "
    "JSON and the auditor's feedback. Rewrite the artifact so it clears {gate} on "
    "EVERY factor ({factors}). Fix exactly what the feedback names, strengthen the "
    "weakest factors first, and preserve everything that already works — do NOT "
    "change the artifact's schema, keys, or structure. Output ONLY the complete, "
    "revised, valid minified JSON artifact. No prose, no markdown fences."
)


def _as_json_text(content) -> str:
    if isinstance(content, str):
        return content
    try:
        return json.dumps(content, ensure_ascii=False)
    except Exception:
        return str(content)


async def polish_pass(kind: str, content, simulate: bool = False,
                      artifact=None, max_passes: int = MAX_POLISH_PASSES) -> dict:
    """Iterate a single artifact against the 95 gate.

    ``content`` may be the artifact JSON string or its parsed object. Returns::

        {
          "content": <best artifact text>,
          "score": <best score>, "passed": bool,
          "passes": [ {pass, score, feedback, factors}, ... ],
          "improved_by": <score delta across the loop>,
          "polished": <bool — at least one rewrite pass ran>,
        }

    Never raises: any polish-pass failure falls back to the best content so far.
    """
    best_content = _as_json_text(content)
    audit = await audit_quality(kind, best_content, simulate=simulate, artifact=artifact)
    passes = [{"pass": 0, "score": audit["score"], "factors": audit.get("factors", {}),
               "feedback": audit.get("feedback", ""), "origin": "initial"}]
    if audit["passed"]:
        return {"content": best_content, "score": audit["score"], "passed": True,
                "passes": passes, "improved_by": 0, "polished": False}

    best_score = audit["score"]
    start_score = audit["score"]
    stale = 0

    for n in range(1, max(1, max_passes) + 1):
        system = _POLISH_SYS.format(gate=MIN_QUALITY, factors=", ".join(QUALITY_FACTORS))
        weakest = sorted((audit.get("factors") or {}).items(),
                         key=lambda kv: kv[1] if isinstance(kv[1], (int, float)) else 0)
        weak_line = ", ".join(f"{k}={v}" for k, v in weakest[:3]) or "unknown"
        prompt = (
            f"Artifact kind: {kind}\n"
            f"Current score: {audit['score']}/100 (gate {MIN_QUALITY}). Weakest factors: {weak_line}.\n"
            f"Auditor feedback: {audit.get('feedback') or 'raise every factor to ' + str(MIN_QUALITY) + '+.'}\n\n"
            f"ARTIFACT TO POLISH:\n{best_content[:6000]}\n\n"
            f"Rewrite it now."
        )
        try:
            routed = await asyncio.to_thread(_llm_in_thread, prompt, system, _GAME_ENSEMBLE)
            candidate = (routed.get("content") or "").strip()
            if not candidate:
                stale += 1
                continue
        except Exception:
            stale += 1
            if stale >= PLATEAU_TOLERANCE:
                break
            continue

        cand_audit = await audit_quality(kind, candidate, simulate=simulate,
                                         artifact=artifact)
        passes.append({"pass": n, "score": cand_audit["score"],
                       "factors": cand_audit.get("factors", {}),
                       "feedback": cand_audit.get("feedback", ""),
                       "origin": f"polish-{n}"})

        if cand_audit["score"] > best_score:
            best_score = cand_audit["score"]
            best_content = candidate
            audit = cand_audit
            stale = 0
        else:
            stale += 1

        if cand_audit["passed"]:
            return {"content": best_content, "score": best_score, "passed": True,
                    "passes": passes, "improved_by": best_score - start_score,
                    "polished": True}
        if stale >= PLATEAU_TOLERANCE:
            break

    return {"content": best_content, "score": best_score,
            "passed": best_score >= MIN_QUALITY, "passes": passes,
            "improved_by": best_score - start_score, "polished": True}
