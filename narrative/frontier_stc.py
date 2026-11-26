"""Frontier level Save The Cat for games.
Maximum precision, full systemic integration, and design law.
"""
from typing import Dict, Any

class FrontierSTC:
    def frontier(self) -> Dict[str, Any]:
        return {
            "law": "Every beat must be expressible as a change in player capability, system state, or meaningful choice. If it cannot, it is not yet adapted.",
            "beats": {
                "opening_image": "0:00-1:00 — core verb succeeds once; world tone established through play, not text",
                "theme_stated": "Systemic pressure (weight, timing, or resource) appears before any explicit statement of the need",
                "setup": "Onboarding ends only when the player has enacted the want successfully three times",
                "catalyst": "Event that makes the current verb set insufficient; new goal is systemically required",
                "debate": "Player can delay but cannot ignore; hesitation has a visible systemic cost",
                "break_into_two": "Irreversible flag or area transition; previous loop is no longer the primary",
                "b_story": "Relationship whose mechanical approval directly modifies the need-pressure systems",
                "fun_and_games": "Full interlock active; every major system feeds the next; promise delivered",
                "midpoint": "Revelation that redefines the win condition; need is now the mechanical bottleneck",
                "bad_guys_close_in": "Costs rise, timers tighten, or opposition scales specifically against ignoring the need",
                "all_is_lost": "Loss of a core capability or resource that the previous strategy depended on",
                "dark_night": "Play is constrained so the only viable actions confront the flaw",
                "break_into_three": "New system or modification unlocks that embodies the integrated lesson",
                "finale": "Single mechanical choice with two irreversible outcomes; both are fully playable consequences",
                "final_image": "Systems and world state visibly reflect the resolution; opening verb feels different"
            },
            "frontier": True,
            "level": "frontier"
        }
