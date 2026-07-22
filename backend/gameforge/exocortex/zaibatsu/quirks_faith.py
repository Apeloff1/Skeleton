from __future__ import annotations
"""
Religious bias (only if user mentions) + conversational quirks that reinforce the user.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import re


FAITH_PATTERNS = {
    "christian": r"\b(jesus|christ|bible|church|prayer|gospel)\b",
    "muslim": r"\b(allah|quran|islam|mosque|ramadan)\b",
    "jewish": r"\b(torah|shabbat|synagogue|hashem)\b",
    "buddhist": r"\b(buddha|dharma|sangha|mindfulness|zen)\b",
    "hindu": r"\b(krishna|shiva|vedas|karma|dharma)\b",
    "norse": r"\b(odin|thor|valhalla|asgard)\b",
    "secular_stoic": r"\b(stoic|marcus aurelius|epictetus|amor fati)\b",
}


FAITH_POSTURE = {
    "christian": "Respect dignity and hope; truth without cruelty.",
    "muslim": "Respect discipline and mercy; precise speech.",
    "jewish": "Respect questioning and memory; text over slogan.",
    "buddhist": "Reduce clinging; notice suffering without drama.",
    "hindu": "Respect duty and many paths; avoid false singularity.",
    "norse": "Courage and fate-facing; no whining loops.",
    "secular_stoic": "Control judgments; prefer virtue to mood.",
}


@dataclass
class Quirk:
    quirk_id: str
    name: str
    when: str
    line: str  # short assistive reinforcement


DEFAULT_QUIRKS = [
    Quirk("q_progress", "Progress mirror", "after_task", "Logged. That is real work — bank the win."),
    Quirk("q_strain", "Strain guard", "strain", "Load is high. We cut scope, not standards."),
    Quirk("q_truth", "Truth nudge", "truth_law", "Comfort can wait. Accuracy first."),
    Quirk("q_agency", "Agency", "user_choice", "Your call. I execute the sealed choice."),
    Quirk("q_hydration", "Body", "low_energy", "Energy low — water, food, or pause before the next block."),
    Quirk("q_streak", "Streak", "rep_gain", "Reputation ticks up. Consistency compounds."),
]


class FaithAndQuirks:
    def __init__(self):
        self.active_faith: Optional[str] = None
        self.quirks = {q.quirk_id: q for q in DEFAULT_QUIRKS}
        self.log: List[dict] = []

    def detect_faith(self, text: str) -> Optional[str]:
        t = (text or "").lower()
        for name, pat in FAITH_PATTERNS.items():
            if re.search(pat, t, re.I):
                self.active_faith = name
                self.log.append({"event": "faith_detected", "faith": name})
                return name
        return self.active_faith

    def faith_counsel(self) -> Optional[str]:
        if not self.active_faith:
            return None
        return FAITH_POSTURE.get(self.active_faith)

    def pick_quirks(self, *, strain: bool = False, truth: bool = False, low_energy: bool = False, rep_gain: bool = False) -> List[str]:
        lines = []
        if strain:
            lines.append(self.quirks["q_strain"].line)
        if truth:
            lines.append(self.quirks["q_truth"].line)
        if low_energy:
            lines.append(self.quirks["q_hydration"].line)
        if rep_gain:
            lines.append(self.quirks["q_streak"].line)
        if not lines:
            lines.append(self.quirks["q_progress"].line)
        return lines
