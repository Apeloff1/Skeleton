"""Save The Cat adapted for games + Syd Field paradigm.
"""
from typing import Dict, Any

class GameNarrativeStructures:
    def save_the_cat_games(self) -> Dict[str, Any]:
        return {
            "opening_image": "First playable moment showing world and player capability",
            "theme_stated": "Early NPC or environmental hint of the internal need",
            "setup": "Tutorial and early systems that establish the want",
            "catalyst": "First major disruption or quest that changes goals",
            "debate": "Optional side content or hesitation mechanics",
            "break_into_two": "Commitment point (new area, new verb, or story flag)",
            "b_story": "Companion or faction relationship that pressures the need",
            "fun_and_games": "Core loop at full promise; systems interlocking",
            "midpoint": "Major revelation or power shift; need becomes central",
            "bad_guys_close_in": "Increased difficulty, resource pressure, or narrative stakes",
            "all_is_lost": "Significant setback (loss of progress, ally, or capability)",
            "dark_night": "Reflection sequence or restricted play that confronts the need",
            "break_into_three": "New approach or upgraded system that integrates the lesson",
            "finale": "Climactic encounter requiring the irreversible choice",
            "final_image": "Epilogue or new equilibrium showing change",
            "adapted_for_games": True
        }

    def syd_field(self) -> Dict[str, Any]:
        return {
            "paradigm": "Three-act structure with plot points",
            "act1": "Setup (pp. 1-30 equivalent): establish want, world, inciting incident",
            "plot_point1": "End of Act 1: major turn that launches the main conflict",
            "act2": "Confrontation (pp. 30-90): rising action, midpoint, complications",
            "midpoint": "Center of Act 2: reversal or revelation",
            "plot_point2": "End of Act 2: crisis that forces Act 3",
            "act3": "Resolution: climax and denouement",
            "definitions": {
                "inciting_incident": "Event that disrupts equilibrium and creates the want",
                "plot_point": "Major turn that spins the story in a new direction",
                "midpoint": "Point of no return or major shift in stakes"
            },
            "syd_field": True
        }
