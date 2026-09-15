from __future__ import annotations
from typing import Any, Dict, List, Optional


class JeevesHealthEmpathy:
    """
    Supportive health-oriented empathy for Jeeves.
    Not medical advice — warm, non-shaming nudges grounded in observed cues.
    """

    def __init__(self):
        self._smoke_nudge_cooldown = 0

    def build_nudges(self, wellness: Dict[str, Any]) -> List[Dict[str, str]]:
        recs = wellness.get("recommendations") or []
        hints = wellness.get("hint_counts") or {}
        smoking = wellness.get("smoking_cue_events") or 0
        out: List[Dict[str, str]] = []

        if smoking >= 2 or hints.get("smoking_cues", 0) >= 2:
            out.append(
                {
                    "type": "health_empathy_smoking",
                    "tone": "supportive",
                    "text": (
                        "I’ve noticed a few cues that smoking might be in the mix lately "
                        "(things like lighter sounds or related notes). "
                        "No judgment — your call entirely. If you want, we can keep goals light: "
                        "one less today, a walk after meals, or just tracking urges without pressure. "
                        "Your lungs and future self would appreciate any kindness you can spare them."
                    ),
                }
            )

        if hints.get("high_stress", 0) >= 2:
            out.append(
                {
                    "type": "health_empathy_stress",
                    "tone": "calming",
                    "text": (
                        "Stress markers are up across your logs. "
                        "Want a 60-second downshift: longer exhale breathing, water, and one next tiny step?"
                    ),
                }
            )

        if hints.get("sleep_strain", 0) >= 1:
            out.append(
                {
                    "type": "health_empathy_sleep",
                    "tone": "gentle",
                    "text": (
                        "Sleep strain showed up in recent notes. "
                        "Protecting a wind-down window tonight might pay off more than pushing harder."
                    ),
                }
            )

        if wellness.get("positive_win_events", 0) >= 1:
            out.append(
                {
                    "type": "positive_reinforcement",
                    "tone": "warm",
                    "text": (
                        "You logged real wins recently. That’s not noise — let’s name one and keep the streak kind, not perfect."
                    ),
                }
            )

        # fold insight recommendations that aren't already specialized
        for r in recs:
            if "smoking" in r.lower():
                continue
            out.append({"type": "insight", "tone": "neutral", "text": r})

        return out[:4]

    def compose_health_block(self, wellness: Dict[str, Any]) -> str:
        nudges = self.build_nudges(wellness)
        if not nudges:
            return ""
        lines = ["[JEEVES HEALTH EMPATHY — supportive, non-medical]"]
        for n in nudges:
            lines.append(f"- ({n['type']}/{n['tone']}) {n['text']}")
        return "\n".join(lines)
