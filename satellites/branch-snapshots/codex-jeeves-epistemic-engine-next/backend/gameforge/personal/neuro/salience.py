from __future__ import annotations
"""
Salience Network — relevance filter for always-on / high-volume text.
Flags keywords, emotional spikes, direct commands; drops data trash.
"""

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


# Default salience lexicon (extendable)
KEYWORD_WEIGHTS: Dict[str, float] = {
    # life / health
    "pain": 0.85, "chest": 0.8, "heart": 0.85, "hospital": 0.95, "doctor": 0.7,
    "sleep": 0.55, "insomnia": 0.75, "exhausted": 0.7, "panic": 0.9, "anxious": 0.7,
    "smoke": 0.65, "lighter": 0.55, "cigarette": 0.7,
    # goals / agency
    "deadline": 0.8, "ship": 0.6, "milestone": 0.65, "court": 0.9, "lawyer": 0.85,
    "remember": 0.7, "important": 0.75, "never forget": 0.95, "critical": 0.8,
    # relational
    "boundary": 0.7, "blocked": 0.6, "apology": 0.55, "threat": 0.9,
    # commands
    "jeeves": 0.9, "remind me": 0.95, "schedule": 0.7, "cancel": 0.65, "note that": 0.8,
}

COMMAND_PATTERNS = [
    r"\bremind me\b",
    r"\bschedule\b",
    r"\bnote that\b",
    r"\bdon't forget\b",
    r"\bjeeves[,:]?\s+",
    r"\badd to (?:my )?(?:log|diary|calendar)\b",
    r"\bmark as (?:done|important)\b",
]

EMOTION_SPIKE_PATTERNS = [
    (r"\b(fuck|shit|damn)\b", 0.45),
    (r"\b(can't|cannot)\s+(do|handle|cope)\b", 0.7),
    (r"\b(love|proud|grateful|relieved)\b", 0.55),
    (r"[!]{2,}", 0.4),
    (r"\b(crying|tears)\b", 0.75),
]

TRASH_PATTERNS = [
    r"^\s*$",
    r"^(um+|uh+|hmm+|ah+)\s*$",
    r"^(yeah|yep|ok|okay|sure|right)\s*$",
    r"grocery|milk|eggs|bread",  # weak unless combined with command
]


@dataclass
class SalienceResult:
    text: str
    score: float
    keep: bool
    reasons: List[str] = field(default_factory=list)
    category: str = "ambient"  # ambient | insight | command | emotional | health
    keywords_hit: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SalienceNetwork:
    def __init__(
        self,
        threshold: float = 0.45,
        keyword_weights: Optional[Dict[str, float]] = None,
    ):
        self.threshold = threshold
        self.keyword_weights = dict(keyword_weights or KEYWORD_WEIGHTS)

    def score(self, text: str) -> SalienceResult:
        raw = text or ""
        t = raw.lower().strip()
        reasons: List[str] = []
        hits: List[str] = []
        score = 0.0
        category = "ambient"

        if not t or len(t) < 3:
            return SalienceResult(raw, 0.0, False, ["empty_or_tiny"], "ambient", [])

        # trash gate (unless command later boosts)
        trash = any(re.search(p, t) for p in TRASH_PATTERNS if p not in (r"grocery|milk|eggs|bread",))
        grocery_only = bool(re.search(r"\b(grocery|milk|eggs|bread)\b", t)) and len(t.split()) < 8

        # keywords
        for kw, w in self.keyword_weights.items():
            if kw in t:
                score += w
                hits.append(kw)
                reasons.append(f"keyword:{kw}")

        # commands
        for p in COMMAND_PATTERNS:
            if re.search(p, t, re.I):
                score += 0.9
                reasons.append("direct_command")
                category = "command"
                break

        # emotional spikes
        for p, w in EMOTION_SPIKE_PATTERNS:
            if re.search(p, t, re.I):
                score += w
                reasons.append("emotion_spike")
                if category == "ambient":
                    category = "emotional"

        # health bias
        if any(h in hits for h in ("pain", "heart", "hospital", "panic", "chest")):
            category = "health"
            score += 0.15
            reasons.append("health_priority")

        if hits and category == "ambient":
            category = "insight"

        # length mild prior (very long monologues get a small bump once)
        if len(t) > 280:
            score += 0.1
            reasons.append("long_form")

        if grocery_only and category != "command":
            score *= 0.25
            reasons.append("likely_list_noise")

        if trash and category == "ambient" and score < self.threshold:
            reasons.append("filler")

        # normalize soft cap
        score = min(1.5, score)
        keep = score >= self.threshold
        return SalienceResult(raw, round(score, 3), keep, reasons, category, hits)

    def filter_batch(self, texts: List[str]) -> Tuple[List[SalienceResult], List[SalienceResult]]:
        kept, dropped = [], []
        for t in texts:
            r = self.score(t)
            (kept if r.keep else dropped).append(r)
        return kept, dropped
