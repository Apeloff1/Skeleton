"""Full Game Creation & Planning Capability — order-of-magnitude expansion.

Production-scale surface covering concept → design → production planning →
asset pipeline → narrative systems → level architecture → QA → release.
Composes with adventure and emulator capabilities. Data-only, fail-closed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

CREATION_SCHEMA = "skeleton.local_model.full_game_creation.v1"


@dataclass
class ProductionPhase:
    name: str
    duration_weeks: int
    deliverables: list[str]
    dependencies: list[str]
    risks: list[str]
    quality_gates: list[str]


@dataclass
class GamePlan:
    title: str
    genre: str
    era: str
    scope: str  # vertical-slice | full | episodic
    phases: list[ProductionPhase]
    team_roles: list[str]
    tech_constraints: list[str]
    success_metrics: list[str]


class FullGameCreationCapability:
    """Order-of-magnitude game creation, planning, and design surface."""

    def __init__(self):
        self.standard_phases = [
            "concept", "pre-production", "vertical-slice", "production",
            "alpha", "beta", "content-lock", "polish", "release-candidate", "ship"
        ]

    def create_master_plan(
        self,
        title: str,
        genre: str = "adventure",
        era: str = "16bit",
        scope: str = "full",
        weeks: int = 52,
    ) -> dict[str, Any]:
        phase_count = 8 if scope == "full" else 5
        phases = []
        for i, name in enumerate(self.standard_phases[:phase_count]):
            phases.append(ProductionPhase(
                name=name,
                duration_weeks=max(2, weeks // phase_count),
                deliverables=[
                    f"{name} design lock",
                    f"{name} asset milestone",
                    f"{name} playable build or doc",
                ],
                dependencies=[self.standard_phases[i-1]] if i else [],
                risks=["scope creep", "asset bottleneck", "technical constraint violation"],
                quality_gates=["design review", "era-authenticity check", "fairness/playtest note"],
            ))
        plan = GamePlan(
            title=title,
            genre=genre,
            era=era,
            scope=scope,
            phases=phases,
            team_roles=["designer", "narrative", "artist", "audio", "producer", "qa"],
            tech_constraints=[
                "target emulator core limits (palette, sprites, resolution)",
                "data-catalog driven content",
                "no unlicensed assets",
                "operator-gated native testing",
            ],
            success_metrics=[
                "vertical slice approved",
                "critical path completable without soft-lock",
                "asset catalog 100% provenance-covered",
                "era constraints respected in final build",
            ],
        )
        return {
            "schema": CREATION_SCHEMA,
            "plan": plan.__dict__ | {"phases": [p.__dict__ for p in phases]},
            "planning_notes": "Phased with explicit gates. Scope can be cut to vertical-slice without breaking later phases.",
        }

    def design_bible_outline(self, title: str, genre: str) -> dict[str, Any]:
        return {
            "title": title,
            "sections": [
                "high concept & pillars",
                "world & lore bible",
                "character roster & arcs",
                "gameplay verbs & systems",
                "level / room architecture standards",
                "puzzle fairness & hint philosophy",
                "narrative delivery (environmental, dialogue, text)",
                "art direction & era style guide",
                "audio direction",
                "UI/UX principles",
                "technical constraints & core targets",
                "asset naming & provenance rules",
                "localization & accessibility notes",
                "QA priorities & known risk areas",
            ],
            "genre": genre,
            "quality_bar": "Every section has measurable acceptance criteria.",
        }

    def production_backlog_template(self, title: str) -> dict[str, Any]:
        epics = [
            "core verb & controls",
            "room graph & navigation",
            "inventory & item states",
            "puzzle framework & first 5 puzzles",
            "dialogue system & flag model",
            "narrative critical path",
            "art pipeline & style lock",
            "audio palette & SFX set",
            "save/flag serialization",
            "QA pass & soft-lock hunt",
            "polish & juice",
            "release packaging & catalog",
        ]
        return {
            "title": title,
            "epics": [{"name": e, "stories": [f"{e} - design", f"{e} - implement", f"{e} - review"]} for e in epics],
            "estimation_note": "Relative sizing only; operator adjusts to real capacity.",
        }

    def asset_pipeline_plan(self, era: str, quality: str = "polished") -> dict[str, Any]:
        return {
            "era": era,
            "quality_tier": quality,
            "stages": [
                "style frame & palette lock",
                "silhouette & readability pass",
                "animation timing charts",
                "environment modular kit",
                "character turnaround & expression set",
                "VFX & interaction feedback",
                "audio stem list & implementation",
                "UI kit",
                "provenance catalog entry for every file",
                "in-engine / core validation pass",
            ],
            "budgets": {
                "sprite_colors": "era-limited",
                "background_layers": "hardware max",
                "sfx_per_interaction": "1-2 distinct",
                "music_stems": "loopable, era-appropriate",
            },
            "gate": "No asset enters final catalog without source identity and license.",
        }

    def narrative_systems_plan(self) -> dict[str, Any]:
        return {
            "delivery_methods": ["environmental", "examine text", "dialogue trees", "item descriptions", "optional logs"],
            "flag_model": "boolean + enum states, namespaced, serializable",
            "branching": "light (major choices only) to preserve critical path clarity",
            "pacing": "setup → complication → midpoint → climax → resolution",
            "tools": "dialogue node editor schema, quest flag checklist, lore consistency pass",
        }

    def qa_and_release_plan(self, title: str) -> dict[str, Any]:
        return {
            "title": title,
            "qa_focus": [
                "critical path completeness",
                "no soft-locks",
                "puzzle fairness (clue visibility)",
                "era constraint violations",
                "save/load integrity",
                "asset provenance completeness",
            ],
            "release_gates": [
                "design bible signed",
                "vertical slice approved",
                "content lock",
                "RC build on target core",
                "catalog & provenance audit",
            ],
            "rollback": "Keep prior phase build; no force-push of content lock.",
        }

    def full_creation_package(self, title: str, genre: str = "adventure", era: str = "16bit") -> dict[str, Any]:
        return {
            "schema": CREATION_SCHEMA,
            "title": title,
            "master_plan": self.create_master_plan(title, genre, era),
            "design_bible": self.design_bible_outline(title, genre),
            "backlog": self.production_backlog_template(title),
            "asset_pipeline": self.asset_pipeline_plan(era),
            "narrative_systems": self.narrative_systems_plan(),
            "qa_release": self.qa_and_release_plan(title),
            "composition_note": "Composes with adventure_game_capability for room/puzzle/dialogue detail and with emulator fleet for target-core constraints.",
        }

    def model_card(self) -> str:
        return (
            "You have a full production-scale game creation and planning capability. "
            "Generate master plans, design bibles, production backlogs, asset pipelines, "
            "narrative system plans, and QA/release gates. All structured, era-aware, "
            "and operator-gated. Composes with adventure design and emulator fleet tools."
        )


def make_full_creation_capability() -> FullGameCreationCapability:
    return FullGameCreationCapability()
