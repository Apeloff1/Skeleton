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

import asyncio

from core.forge_quality_contract import artifact_text, compatible_rewrite, source_digest
from fastapi import HTTPException

from routes.quality import audit_quality, MIN_QUALITY, QUALITY_FACTORS
from routes.playable import PlayableModelFailure, _GAME_ENSEMBLE, _llm_in_thread

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


def _result(content: str, audit: dict, passes: list[dict], start_score: int,
            *, attempted: bool) -> dict:
    digest = source_digest(content) if content else ""
    exact = audit.get("source_sha256") == digest
    passed = (
        exact and audit.get("audit_complete") is True
        and audit.get("passed") is True and audit["score"] >= MIN_QUALITY
    )
    return {
        "content": content, "score": audit["score"] if exact else 0, "passed": passed,
        "passes": passes, "improved_by": max(0, audit["score"] - start_score) if exact else 0,
        "polished": attempted, "source_sha256": digest,
        "audit_complete": exact and audit.get("audit_complete") is True,
        "evidence_scope": "model-review-structural-proxy",
    }


def _trail(n: int, audit: dict, *, accepted: bool) -> dict:
    return {
        "pass": n, "score": audit["score"], "factors": audit.get("factors", {}),
        "feedback": audit.get("feedback", ""), "origin": "initial" if n == 0 else f"polish-{n}",
        "accepted": accepted, "audit_complete": audit.get("audit_complete") is True,
        "source_sha256": audit.get("source_sha256", ""),
    }


async def polish_pass(kind: str, content, simulate: bool = False,
                      artifact=None, max_passes: int = MAX_POLISH_PASSES) -> dict:
    """Preserve the exact best fully audited, schema-compatible artifact.

    A structural proxy is not actual engine qualification. Failed rewrites
    never replace a better source, and the winning observation must identify
    the same bytes that are returned or persisted.
    """
    del artifact
    if type(max_passes) is not int or not 1 <= max_passes <= 10:
        raise ValueError("max_passes must be an integer from one to ten")
    if type(kind) is not str or not 1 <= len(kind) <= 128:
        raise ValueError("invalid artifact kind")
    try:
        best_content, original = artifact_text(content)
    except ValueError:
        return _result("", {"score": 0, "source_sha256": ""}, [], 0, attempted=False)

    audit = await audit_quality(kind, best_content, simulate=simulate)
    start_score = audit["score"]
    passes = [_trail(0, audit, accepted=True)]
    if audit["passed"] or not audit.get("audit_complete"):
        return _result(best_content, audit, passes, start_score, attempted=False)

    stale = 0
    attempted = False
    for n in range(1, max_passes + 1):
        system = _POLISH_SYS.format(gate=MIN_QUALITY, factors=", ".join(QUALITY_FACTORS))
        weakest = sorted(audit["factors"].items(), key=lambda item: item[1])
        weak_line = ", ".join(f"{key}={value}" for key, value in weakest[:3])
        prompt = (
            f"Artifact kind: {kind}\n"
            f"Current score: {audit['score']}/100. Weakest factors: {weak_line}.\n"
            f"Auditor feedback: {audit.get('feedback', '')}\n\n"
            f"COMPLETE ARTIFACT TO POLISH:\n{best_content}\n\nRewrite it now."
        )
        attempted = True
        candidate = ""
        try:
            routed = await asyncio.to_thread(_llm_in_thread, prompt, system, _GAME_ENSEMBLE)
            candidate, proposed = artifact_text(routed.get("content", ""))
            if type(content) in (dict, list):
                candidate, proposed = artifact_text(proposed)
            if not compatible_rewrite(original, proposed):
                raise ValueError("schema changed")
        except (HTTPException, PlayableModelFailure):
            raise
        except Exception:
            passes.append(_trail(n, {
                "score": 0, "feedback": "Rewrite unavailable or incompatible with original structure",
                "source_sha256": source_digest(candidate) if candidate else "",
            }, accepted=False))
            stale += 1
        else:
            # Never simulate the initial artifact while auditing new bytes.
            candidate_audit = await audit_quality(kind, candidate, simulate=simulate)
            improved = (
                candidate_audit.get("audit_complete") is True
                and candidate_audit.get("source_sha256") == source_digest(candidate)
                and candidate_audit["score"] > audit["score"]
            )
            passes.append(_trail(n, candidate_audit, accepted=improved))
            if improved:
                best_content, audit, stale = candidate, candidate_audit, 0
            else:
                stale += 1
        if audit["passed"] or stale >= PLATEAU_TOLERANCE:
            break

    return _result(best_content, audit, passes, start_score, attempted=attempted)
