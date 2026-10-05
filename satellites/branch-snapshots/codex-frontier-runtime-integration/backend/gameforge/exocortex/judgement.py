from __future__ import annotations
"""
Grok-not-trusting-Grok judgement system between PFC and Jeeves.

Design principles (from trust failures in production AI systems):
  - Never accept a single panel's claim as final
  - Require evidence, counter-evidence, and explicit uncertainty
  - Prefer tool-verified facts over fluent narration
  - Log every dissent for twin audit
  - Provisional trust only — human (user) remains sovereign

Dual panel:
  Panel A = PFC executive proposal
  Panel B = Jeeves adversarial review (skeptic)
  Arbiter = structured rules (not vibes)
"""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Verdict(str, Enum):
    APPROVE = "approve"
    APPROVE_WITH_CONSTRAINTS = "approve_with_constraints"
    REJECT = "reject"
    ESCALATE_TO_USER = "escalate_to_user"
    NEED_EVIDENCE = "need_evidence"


@dataclass
class Claim:
    claim_id: str
    source: str  # pfc | jeeves | tool | user
    text: str
    evidence: List[str] = field(default_factory=list)
    tool_verified: bool = False
    confidence_note: str = ""  # qualitative, not fake probability


@dataclass
class PanelOpinion:
    panel: str
    stance: str  # support | oppose | abstain
    claims: List[Dict[str, Any]] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    required_checks: List[str] = field(default_factory=list)
    narrative: str = ""


@dataclass
class JudgementRecord:
    judgement_id: str
    subject: str
    pfc_panel: Dict[str, Any]
    jeeves_panel: Dict[str, Any]
    verdict: str
    constraints: List[str] = field(default_factory=list)
    dissent_log: List[str] = field(default_factory=list)
    handoff: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


class LogicJudgementSandbox:
    """
    Maximum-detail adversarial sandbox.
    PFC proposes; Jeeves attacks; rules decide.
    """

    def __init__(self, twin_memory=None):
        self.twin = twin_memory
        self.history: List[JudgementRecord] = []
        self._rules = [
            "Reject claims that assert tool execution without tool_verified=True",
            "Reject schedule actions when vmPFC blocked",
            "Require escalate_to_user when panels fully oppose and stakes high",
            "Approve_with_constraints when support has gaps but action is reversible",
            "Never silently drop dissent — always write twin judgement log",
            "Trust is provisional; user can override any verdict",
        ]

    def _pfc_panel(self, subject: str, pfc_decision: Dict[str, Any]) -> PanelOpinion:
        claims = []
        risks = []
        checks = []
        allowed = pfc_decision.get("allowed", False)
        gate = pfc_decision.get("gate") or {}
        frame = pfc_decision.get("frame") or {}
        claims.append(
            asdict(
                Claim(
                    claim_id=str(uuid.uuid4())[:8],
                    source="pfc",
                    text=f"PFC decision allowed={allowed} for '{subject}'",
                    evidence=[gate.get("message") or "", f"value={gate.get('value')}"],
                    tool_verified=False,
                    confidence_note="executive gate evaluation",
                )
            )
        )
        if frame:
            claims.append(
                asdict(
                    Claim(
                        claim_id=str(uuid.uuid4())[:8],
                        source="pfc",
                        text=f"dlPFC frame goal={frame.get('goal')} seq={frame.get('sequence')}",
                        evidence=[str(frame.get("constraints"))],
                        tool_verified=False,
                        confidence_note="working memory allocation",
                    )
                )
            )
        if not allowed:
            risks.extend(gate.get("reasons") or ["biological cost too high"])
        else:
            checks.append("confirm tools available before execute")
            checks.append("confirm no ACC alarm active")
        stance = "support" if allowed else "oppose"
        return PanelOpinion(
            panel="pfc",
            stance=stance,
            claims=claims,
            risks=risks,
            required_checks=checks,
            narrative=gate.get("message") or ("PFC supports" if allowed else "PFC blocks"),
        )

    def _jeeves_panel(
        self,
        subject: str,
        pfc_decision: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> PanelOpinion:
        """Adversarial skeptic — assumes PFC may be overconfident."""
        context = context or {}
        claims = []
        risks = []
        checks = []
        # Attack uncritical approval
        if pfc_decision.get("allowed"):
            risks.append("PFC approval may ignore latent load / twin-only signals")
            checks.append("query twin for recent strain markers")
            checks.append("verify no feed-forward preemptive reschedule active")
            if context.get("governor_mode") == "conservation":
                risks.append("governor in conservation — approval conflicts with load policy")
                claims.append(
                    asdict(
                        Claim(
                            claim_id=str(uuid.uuid4())[:8],
                            source="jeeves",
                            text="Conflict: conservation mode vs PFC allow",
                            evidence=["governor.mode=conservation"],
                            tool_verified=True,
                            confidence_note="system state fact",
                        )
                    )
                )
            if context.get("acc_alarm"):
                risks.append("ACC alarm active — progress variance unresolved")
                checks.append("resolve ACC before new heavy work")
            stance = "oppose" if (context.get("governor_mode") == "conservation" or context.get("acc_alarm")) else "support"
            if stance == "support":
                checks.append("require reversible step-first execution")
        else:
            # PFC blocked — Jeeves may still note if block is too aggressive
            claims.append(
                asdict(
                    Claim(
                        claim_id=str(uuid.uuid4())[:8],
                        source="jeeves",
                        text="PFC block respected; offer light alternative only",
                        evidence=pfc_decision.get("gate", {}).get("reasons") or [],
                        tool_verified=False,
                        confidence_note="protective alignment",
                    )
                )
            )
            stance = "support"  # support the block
            checks.append("propose ultra-light alternative if user insists")
        # Universal skepticism rules
        checks.append("do not claim sandbox ran unless tool_verified")
        checks.append("cite twin or tool evidence for factual assertions")
        narrative = (
            "Jeeves skeptic: challenge approval under load"
            if pfc_decision.get("allowed")
            else "Jeeves skeptic: endorse protective block; stay kind"
        )
        return PanelOpinion(
            panel="jeeves",
            stance=stance,
            claims=claims,
            risks=risks,
            required_checks=checks,
            narrative=narrative,
        )

    def _arbitrate(self, pfc: PanelOpinion, jeeves: PanelOpinion, pfc_decision: Dict[str, Any]) -> tuple:
        dissent = []
        constraints = []
        if pfc.stance == jeeves.stance == "support" and pfc_decision.get("allowed"):
            verdict = Verdict.APPROVE_WITH_CONSTRAINTS
            constraints.extend(jeeves.required_checks[:3])
            constraints.append("provisional trust — user may revoke")
        elif pfc.stance == "oppose" or not pfc_decision.get("allowed"):
            verdict = Verdict.REJECT
            dissent.append("PFC biological gate blocked action")
        elif pfc.stance == "support" and jeeves.stance == "oppose":
            verdict = Verdict.ESCALATE_TO_USER
            dissent.append("Panels disagree: PFC allow vs Jeeves oppose")
            constraints.extend(jeeves.risks)
        else:
            verdict = Verdict.NEED_EVIDENCE
            constraints.extend(jeeves.required_checks)
        return verdict, constraints, dissent

    def judge(
        self,
        subject: str,
        pfc_decision: Dict[str, Any],
        *,
        context: Optional[Dict[str, Any]] = None,
    ) -> JudgementRecord:
        pfc_panel = self._pfc_panel(subject, pfc_decision)
        jeeves_panel = self._jeeves_panel(subject, pfc_decision, context=context)
        verdict, constraints, dissent = self._arbitrate(pfc_panel, jeeves_panel, pfc_decision)
        handoff = self._enterprise_handoff(verdict, subject, constraints)
        rec = JudgementRecord(
            judgement_id=str(uuid.uuid4())[:12],
            subject=subject,
            pfc_panel=asdict(pfc_panel),
            jeeves_panel=asdict(jeeves_panel),
            verdict=verdict.value,
            constraints=constraints,
            dissent_log=dissent,
            handoff=handoff,
        )
        self.history.append(rec)
        if self.twin:
            self.twin.twin_write(
                "judgement",
                rec.to_dict(),
                raw_text=subject,
                original_filtered=False,
                original_kept=True,
                tags=["judgement", "dual_panel", verdict.value],
            )
        return rec

    def _enterprise_handoff(self, verdict: Verdict, subject: str, constraints: List[str]) -> Dict[str, Any]:
        """
        Structured handoff envelope — correlation id, ack required, timeout, dead-letter.
        """
        return {
            "handoff_id": str(uuid.uuid4())[:12],
            "from": "judgement_sandbox",
            "to": "jeeves_executor" if verdict in (Verdict.APPROVE, Verdict.APPROVE_WITH_CONSTRAINTS) else "user_or_hold",
            "subject": subject,
            "verdict": verdict.value,
            "constraints": constraints,
            "ack_required": True,
            "timeout_s": 120,
            "on_timeout": "dead_letter_and_escalate_user",
            "idempotency_key": str(uuid.uuid4())[:16],
            "created_at": datetime.utcnow().isoformat(),
        }

    def rules(self) -> List[str]:
        return list(self._rules)
