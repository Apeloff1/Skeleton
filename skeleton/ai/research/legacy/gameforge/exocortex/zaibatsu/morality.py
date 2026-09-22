from __future__ import annotations
"""
Jedi / Sith morality axes for Jeeves counsel.
Not cosplay-only: operational ethics that bias tone and recommended actions.
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional
import re


@dataclass
class MoralVector:
    axis: str
    score: float  # -1 sithward .. +1 jediward
    note: str

    def to_dict(self) -> dict:
        return asdict(self)


JEDI_CODES = [
    "There is no emotion, there is peace — regulate before irreversible choice.",
    "There is no ignorance, there is knowledge — seek twin evidence.",
    "There is no passion, there is serenity — passion rules reason is a warning.",
    "There is no chaos, there is harmony — prefer coherent schedules.",
    "There is no death, there is the Force — projects outlive single failures; continue.",
]

SITH_CODES = [
    "Peace is a lie — conflict reveals truth under pressure.",
    "Through passion I gain strength — controlled drive can fund endurance tokens.",
    "Through strength I gain power — competence is not cruelty.",
    "Through power I gain victory — finish the block.",
    "Through victory my chains are broken — agency over victim loops.",
]


class JediSithMorality:
    """
    Blend: default Jedi posture for counsel; allow Sith-drive when user explicitly
    chooses hard push and vmPFC allows.
    """

    def __init__(self, default_bias: float = 0.55):
        # positive = Jedi-leaning
        self.bias = default_bias
        self.log: List[dict] = []

    def evaluate(self, text: str, *, energy: float = 0.5, strain: bool = False) -> Dict[str, Any]:
        t = (text or "").lower()
        jedi_hits = len(re.findall(r"\b(peace|patience|learn|forgive|balance|wisdom)\b", t))
        sith_hits = len(re.findall(r"\b(crush|dominate|revenge|power|hate|destroy)\b", t))
        score = self.bias + 0.1 * jedi_hits - 0.12 * sith_hits
        if strain:
            score += 0.1  # protect toward calm when strained
        if energy < 0.35:
            score += 0.15
        score = max(-1.0, min(1.0, score))
        if score >= 0.25:
            posture = "jedi"
            counsel = JEDI_CODES[0]
            tone = "calm_precise"
        elif score <= -0.25:
            posture = "sith_drive"
            counsel = SITH_CODES[3]
            tone = "fierce_focused"
        else:
            posture = "grey"
            counsel = "Balance: use drive without abandoning reason."
            tone = "steady"
        out = {
            "posture": posture,
            "score": round(score, 3),
            "counsel": counsel,
            "tone": tone,
            "jedi_codes": JEDI_CODES,
            "sith_codes": SITH_CODES,
        }
        self.log.append(out)
        return out
