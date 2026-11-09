from __future__ import annotations
"""
Left-brain (digital reductionist) and Right-brain (analog synthesizer) sandboxes.
Both parse the same input; bridge merges certainty + context for Jeeves.
"""

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class HemisphereParse:
    hemisphere: str  # left | right
    tokens: List[str] = field(default_factory=list)
    structures: Dict[str, Any] = field(default_factory=dict)
    relations: List[str] = field(default_factory=list)
    tone_cues: List[str] = field(default_factory=list)
    summary: str = ""
    confidence: float = 1.0  # left prefers 1.0 exact; right may be softer but not probabilistic policy

    def to_dict(self) -> dict:
        return asdict(self)


class LeftBrainSandbox:
    """
    Digital, sequential, literal.
    Extracts numbers, dates, commands, ordered steps, exact keywords.
    """

    CMD = re.compile(
        r"\b(remind me|schedule|calculate|prove|ship|deadline|milestone|percent|%|block)\b",
        re.I,
    )
    NUM = re.compile(r"[-+]?\d+(?:\.\d+)?%?")
    STEP = re.compile(r"(?:^|\n)\s*(?:\d+[.)]|[-*])\s+(.+)")

    def parse(self, text: str) -> HemisphereParse:
        t = text or ""
        nums = self.NUM.findall(t)
        cmds = self.CMD.findall(t)
        steps = self.STEP.findall(t)
        tokens = re.findall(r"[A-Za-z0-9_%]+", t)
        structures = {
            "numbers": nums,
            "commands": [c.lower() for c in cmds],
            "steps": steps,
            "literal_length": len(t),
            "has_math_hint": bool(re.search(r"[=+\-*/]|pow|shard|lean|sympy", t, re.I)),
        }
        summary = (
            f"LEFT: cmds={structures['commands']} nums={nums[:8]} steps={len(steps)}"
        )
        return HemisphereParse(
            hemisphere="left",
            tokens=tokens[:80],
            structures=structures,
            relations=[],
            tone_cues=[],
            summary=summary,
            confidence=1.0,
        )


class RightBrainSandbox:
    """
    Holistic, relational, tonal.
    Extracts mood/energy language, continuity, social context, whole-message vibe.
    """

    TONE = [
        (r"\b(exhausted|tired|drained)\b", "low_energy"),
        (r"\b(proud|grateful|relieved|calm)\b", "positive"),
        (r"\b(frustrated|stuck|overwhelmed|angry)\b", "strain"),
        (r"\b(lonely|isolated)\b", "social_low"),
        (r"\b(together|we|team)\b", "social_high"),
        (r"\b(noise|loud|chaotic)\b", "sensory_load"),
        (r"\b(quiet|peaceful)\b", "sensory_ease"),
        (r"\b(remember when|same as|again|pattern)\b", "continuity"),
    ]

    def parse(self, text: str) -> HemisphereParse:
        t = (text or "").lower()
        cues = []
        for pat, label in self.TONE:
            if re.search(pat, t):
                cues.append(label)
        relations = []
        if "continuity" in cues:
            relations.append("links_to_prior_experience")
        if "strain" in cues and "low_energy" in cues:
            relations.append("compounding_load")
        if "sensory_load" in cues:
            relations.append("environment_matters")
        # holistic field
        structures = {
            "cue_set": cues,
            "wholeness": "high" if len(t) > 120 else "compact",
            "relational_density": len(relations),
        }
        summary = f"RIGHT: cues={cues} relations={relations}"
        return HemisphereParse(
            hemisphere="right",
            tokens=[],
            structures=structures,
            relations=relations,
            tone_cues=cues,
            summary=summary,
            confidence=0.9 if cues else 0.7,
        )


class BilateralBridge:
    """
    Forces handshake: left structures + right context → coherent directive.
    """

    def __init__(self):
        self.left = LeftBrainSandbox()
        self.right = RightBrainSandbox()
        self.logs: List[Dict[str, Any]] = []

    def parse_both(self, text: str) -> Dict[str, Any]:
        L = self.left.parse(text)
        R = self.right.parse(text)
        directive = self._merge(L, R)
        out = {
            "left": L.to_dict(),
            "right": R.to_dict(),
            "bridge": directive,
            "ts": datetime.utcnow().isoformat(),
        }
        self.logs.append({"event": "bilateral_parse", "bridge": directive})
        if len(self.logs) > 2000:
            self.logs = self.logs[-2000:]
        return out

    def _merge(self, L: HemisphereParse, R: HemisphereParse) -> Dict[str, Any]:
        mode = "balanced"
        actions: List[str] = []
        if R.tone_cues and "strain" in R.tone_cues:
            mode = "protect_then_execute"
            actions.append("shorten_commands")
        if L.structures.get("commands"):
            actions.append("execute_literal_commands")
        if L.structures.get("has_math_hint"):
            actions.append("route_math_exocortex")
        if "continuity" in R.tone_cues:
            actions.append("query_semantic_memory")
        if "sensory_load" in R.tone_cues:
            actions.append("raise_ras_threshold")
        if not actions:
            actions.append("log_and_continue")
        return {
            "mode": mode,
            "actions": actions,
            "left_summary": L.summary,
            "right_summary": R.summary,
            "jeeves_tone": (
                "warm_and_precise"
                if "positive" in R.tone_cues
                else "gentle_and_precise"
                if "strain" in R.tone_cues or "low_energy" in R.tone_cues
                else "clear_and_steady"
            ),
        }
