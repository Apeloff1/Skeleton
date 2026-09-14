"""Knowledge-augmented deterministic reasoning frames for Jeeves.

This kernel does not impersonate an LLM. It prepares high-quality epistemic
context for any reasoning model/agent: known claims, unresolved gaps, evidence
coverage, risk flags and a plan/review scaffold. Every prompt is also fed back to
Curiosity so idle cycles can deepen the subjects users actually care about.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.curiosity_engine import CuriosityEngine


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _attest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sentences(text: str, *, limit: int = 16) -> list[str]:
    out = [" ".join(x.split()).strip() for x in re.split(r"(?<=[.!?])\s+|\n+", text) if x.strip()]
    return out[:limit]


class KnowledgeAugmentedJeeves:
    def __init__(self, curiosity: CuriosityEngine) -> None:
        self.curiosity = curiosity

    def _context(
        self,
        prompt: str,
        *,
        user_scope: str = "default",
        signal_key: str | None = None,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        signal = self.curiosity.observe_prompt(
            prompt,
            user_scope=user_scope,
            signal_key=signal_key,
            observed_at=observed_at,
        )
        # Always call the engine-level projection. VerifiedCuriosityEngine
        # overrides this to enforce expiry/retraction/current truth state; using
        # fabric.orientation_pack directly would bypass that safety boundary.
        pack = self.curiosity.orientation_pack(prompt, limit=8)
        return {"signal_id": signal.id, "subject": signal.subject, "orientation": pack}

    @staticmethod
    def _signal_args(payload: dict[str, Any]) -> dict[str, Any]:
        key = str(payload.get("_curiosity_signal_key") or "").strip() or None
        observed_at = str(payload.get("_curiosity_observed_at") or "").strip() or None
        return {
            "user_scope": str(payload.get("user_scope") or "default"),
            "signal_key": key,
            "observed_at": observed_at,
        }

    def reason(self, payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(payload.get("prompt") or payload.get("question") or payload.get("task") or "").strip()
        if not prompt:
            raise ValueError("reasoning prompt is required")
        ctx = self._context(prompt, **self._signal_args(payload))
        orientation = ctx["orientation"]
        known = list(orientation["claims"])
        unresolved = list(orientation["unresolved"])
        frame = {
            "prompt": prompt[:20_000],
            "subject": ctx["subject"],
            "knowledge_record_ids": orientation["record_ids"],
            "known_claims": known,
            "unresolved": unresolved,
            "confidence_floor": orientation["confidence_floor"],
            "reasoning_directives": [
                "Separate retrieved knowledge from new inference.",
                "Treat unresolved items as questions, not facts.",
                "Prefer evidence-backed claims over fluent speculation.",
                "Expose assumptions that materially affect the answer.",
                "Feed newly discovered gaps back into Curiosity.",
            ],
            "epistemic_state": (
                "grounded" if known and orientation["confidence_floor"] >= 0.65
                else "partial" if known else "frontier"
            ),
            "curiosity_signal_id": ctx["signal_id"],
        }
        frame["attestation_sha256"] = _attest(frame)
        return frame

    def plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        goal = str(payload.get("goal") or payload.get("prompt") or payload.get("task") or "").strip()
        if not goal:
            raise ValueError("planning goal is required")
        reason = self.reason({**payload, "prompt": goal})
        known = reason["known_claims"]
        unresolved = reason["unresolved"]
        phases = [
            {"id": "orient", "purpose": "retrieve existing knowledge and constraints", "inputs": reason["knowledge_record_ids"], "exit": "working context assembled"},
            {"id": "resolve", "purpose": "resolve highest-impact gaps before commitment", "questions": unresolved[:8], "exit": "blocking uncertainty reduced"},
            {"id": "decompose", "purpose": "split the goal into independently verifiable work units", "exit": "ordered work graph produced"},
            {"id": "execute", "purpose": "execute with evidence capture and checkpoints", "exit": "artifacts/results produced"},
            {"id": "verify", "purpose": "challenge results against known claims, constraints and failure modes", "exit": "reviewed result or explicit residual risk"},
            {"id": "learn", "purpose": "publish durable lessons and new gaps back to Curiosity", "exit": "knowledge surfaces updated"},
        ]
        result = {
            "goal": goal[:20_000],
            "subject": reason["subject"],
            "epistemic_state": reason["epistemic_state"],
            "known_context": known[:16],
            "blocking_questions": unresolved[:12],
            "phases": phases,
            "knowledge_record_ids": reason["knowledge_record_ids"],
            "curiosity_signal_id": reason["curiosity_signal_id"],
        }
        result["attestation_sha256"] = _attest(result)
        return result

    def review(self, payload: dict[str, Any]) -> dict[str, Any]:
        subject_prompt = str(payload.get("prompt") or payload.get("goal") or payload.get("subject") or "").strip()
        candidate = str(payload.get("candidate") or payload.get("answer") or payload.get("output") or "").strip()
        if not subject_prompt or not candidate:
            raise ValueError("review requires prompt/subject and candidate output")
        ctx = self._context(subject_prompt, **self._signal_args(payload))
        pack = ctx["orientation"]
        candidate_lc = candidate.casefold()
        matched = [claim for claim in pack["claims"] if any(token in candidate_lc for token in re.findall(r"[a-z0-9]{4,}", claim.casefold())[:6])]
        unresolved_mentions = [gap for gap in pack["unresolved"] if any(token in candidate_lc for token in re.findall(r"[a-z0-9]{4,}", gap.casefold())[:6])]
        assertions = _sentences(candidate, limit=24)
        support_ratio = min(1.0, len(matched) / max(1, min(len(assertions), 8))) if pack["claims"] else 0.0
        risk_flags: list[str] = []
        if not pack["record_ids"]:
            risk_flags.append("no_retrieved_knowledge")
        if pack["unresolved"] and not unresolved_mentions:
            risk_flags.append("known_uncertainty_not_acknowledged")
        if len(assertions) >= 8 and support_ratio < 0.25:
            risk_flags.append("high_assertion_low_support")
        result = {
            "subject": ctx["subject"],
            "candidate_length": len(candidate),
            "assertion_count": len(assertions),
            "knowledge_record_ids": pack["record_ids"],
            "matched_known_claims": matched[:12],
            "known_uncertainties_mentioned": unresolved_mentions[:12],
            "support_ratio": round(support_ratio, 4),
            "risk_flags": risk_flags,
            "verdict": "needs_review" if risk_flags else "context_aligned",
            "curiosity_signal_id": ctx["signal_id"],
        }
        result["attestation_sha256"] = _attest(result)
        return result
