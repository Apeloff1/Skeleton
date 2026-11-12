"""Longform relevant knowledge dump.
Extensive treatment of game theory, systems design, and advanced game building.
"""
from typing import Dict, Any

class LongformKnowledge:
    def dump(self) -> Dict[str, Any]:
        return {
            "game_theory": {
                "nash_equilibrium": "A strategy profile where no player can improve their payoff by unilaterally changing strategy, holding others fixed. In game systems this means interlocking mechanics are stable: changing one system in isolation does not yield better outcomes for the player or the designer.",
                "evolutionary_stable_strategy": "A strategy that, if adopted by a population, cannot be invaded by a rare mutant strategy. In design terms, the core loop and progression should be ESS: alternative playstyles do not dominate once the intended systems are engaged.",
                "replicator_dynamics": "The equation dx/dt = x(1-x)Δπ describes how the proportion of a strategy changes. Higher-payoff strategies grow. Applied to games, this suggests tuning so that skilled or intended play has higher effective payoff, causing the population of player behaviors to converge on mastery.",
                "hawk_dove": "Models conflict over a resource. When cost of fighting exceeds value, mixed ESS emerges. Useful for designing risk-reward in combat or resource contention so that pure aggression is not always dominant.",
                "prisoners_dilemma": "One-shot favors defection. Repeated interactions with reciprocity (Tit-for-Tat) can sustain cooperation as ESS. Design multiplayer or systemic interactions with memory and consequence to enable cooperative equilibria."
            },
            "systems_design": {
                "interlock": "Inventory constrains loadout. Combat consumes inventory and produces progression currency. Progression gates both new verbs and narrative beats. Narrative reframes the meaning of earlier systems. Each feeds the next so that no system is optional flavor.",
                "rhythmic": "Sync player actions to an audio or visual pulse. Perfect timing within a window grants bonus damage, resource, or information. Creates flow state and a skill ceiling based on timing mastery rather than pure stats.",
                "clever_inventory": "Items have weight, rarity, and adjacency effects. Placing complementary items next to each other triggers combo modifiers. Weight limit forces meaningful exclusion. Emergent builds arise from spatial arrangement rather than flat lists."
            },
            "narrative_and_presentation": {
                "want_need": "External concrete want established early. Internal contradictory need revealed through pressure. Midpoint makes the want achievable only by confronting the need. Climax is a choice that cannot satisfy both. Theme is the residue of the payment.",
                "cinematic": "Wide shots teach geography. Medium shots hold performance. Close-ups reserve for emotional peaks. Camera movement only when following intent, revealing information, or heightening feeling. Three-point lighting keeps subject readable and separated.",
                "music": "Short melodic cells for characters and themes. Cells combine, fragment, and transform. Orchestration scales with dramatic weight. Hits are frame-accurate. Transitions hide inside action or dialogue so the score feels inevitable."
            },
            "longform": True,
            "relevant": True,
            "extensive": True
        }
