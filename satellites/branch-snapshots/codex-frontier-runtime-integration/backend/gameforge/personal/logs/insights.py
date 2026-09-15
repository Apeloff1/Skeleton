from __future__ import annotations
import re
from typing import Any, Dict, List
from collections import Counter

from gameforge.personal.logs.kinds import PersonalLogKind, PersonalLogEntry


# Patterns used for gentle wellness / health empathy (not medical diagnosis)
HEALTH_PATTERNS = {
    "smoking_cues": [
        r"\blighter\b",
        r"\bcigarette\b",
        r"\bsmok(e|ing|ed)\b",
        r"\bvape\b",
        r"\bnicotine\b",
        r"\bashtray\b",
    ],
    "sleep_strain": [r"\binsomnia\b", r"\bdidn'?t sleep\b", r"\bexhausted\b", r"\bwired at night\b"],
    "high_stress": [r"\bpanic\b", r"\boverwhelm(ed)?\b", r"\bcan'?t cope\b", r"\bburnout\b"],
    "low_mood": [r"\bhopeless\b", r"\bworthless\b", r"\bempty\b", r"\bnumb\b"],
    "positive_wins": [r"\bproud\b", r"\bfinished\b", r"\bshipped\b", r"\bgrateful\b", r"\bcalm\b"],
}


class InsightEngine:
    def extract_hints(self, kind: PersonalLogKind, body: str, metadata: Dict[str, Any]) -> List[str]:
        text = (body or "").lower()
        hints: List[str] = []
        for label, patterns in HEALTH_PATTERNS.items():
            for p in patterns:
                if re.search(p, text, re.I):
                    hints.append(label)
                    break
        if kind == PersonalLogKind.COGNITIVE_BIAS:
            hints.append("cognitive_reframe_opportunity")
        if kind == PersonalLogKind.INTEROCEPTION and metadata.get("energy") is not None:
            try:
                if float(metadata["energy"]) < 0.3:
                    hints.append("low_energy")
            except Exception:
                pass
        if kind == PersonalLogKind.SOCIAL_BOUNDARY and metadata.get("boundary"):
            hints.append("boundary_work")
        if kind == PersonalLogKind.PROSPECT:
            hints.append("future_focus")
        if kind == PersonalLogKind.STIMULUS_RESPONSE:
            hints.append("agency_choice")
        return list(dict.fromkeys(hints))

    def summarize(self, entries_by_kind: Dict[PersonalLogKind, List[PersonalLogEntry]]) -> Dict[str, Any]:
        all_hints: Counter = Counter()
        mood_vals: List[float] = []
        smoking_hits = 0
        wins = 0
        for kind, rows in entries_by_kind.items():
            for e in rows[-30:]:
                for h in e.insight_hints:
                    all_hints[h] += 1
                if e.mood is not None:
                    mood_vals.append(e.mood)
                if "smoking_cues" in e.insight_hints:
                    smoking_hits += 1
                if "positive_wins" in e.insight_hints:
                    wins += 1
        avg_mood = sum(mood_vals) / len(mood_vals) if mood_vals else None
        return {
            "hint_counts": dict(all_hints.most_common(12)),
            "avg_mood": avg_mood,
            "smoking_cue_events": smoking_hits,
            "positive_win_events": wins,
            "recommendations": self._recommendations(all_hints, smoking_hits, avg_mood, wins),
        }

    def _recommendations(
        self, hints: Counter, smoking_hits: int, avg_mood: float | None, wins: int
    ) -> List[str]:
        recs: List[str] = []
        if smoking_hits >= 2:
            recs.append(
                "Health empathy: multiple smoking-related cues logged. "
                "Offer a supportive, non-shaming nudge toward reducing or quitting when the moment is calm."
            )
        if hints.get("high_stress", 0) >= 2:
            recs.append("Stress load looks elevated — prefer short grounding prompts over heavy tasks.")
        if hints.get("low_energy", 0) >= 2:
            recs.append("Energy notes are low — suggest lighter plans and recovery windows.")
        if hints.get("cognitive_reframe_opportunity", 0) >= 1:
            recs.append("Cognitive bias entries present — invite one kind reframe, not debate.")
        if wins >= 1:
            recs.append("Reinforce recent wins explicitly; bank them into retrospect/accomplishment tone.")
        if avg_mood is not None and avg_mood < -0.25:
            recs.append("Mood trend soft — lead with warmth and one next kind step.")
        if not recs:
            recs.append("No acute flags — keep encouragement light and competence-focused.")
        return recs
