"""Authored gameplay-form and continuation laws for the million-world forge.

Ten substantive play forms and twelve progression contracts. These are rule
templates, not ten thousand manually written games. A playable generic adapter
must implement each form's actual constraints and outcomes before claiming
coverage. Art style, era, hardware, seeds and resolution are NEVER count factors.
"""
from __future__ import annotations

from dataclasses import dataclass

PLAY_FORMS_VERSION = "original-play-forms.v1"


@dataclass(frozen=True)
class PlayForm:
    form_id: str
    title: str
    player_loop: str
    win_criterion: str
    difficulty_pressure: str
    control_law: str
    mechanics: tuple[str, ...]


@dataclass(frozen=True)
class ProgressionLaw:
    arc_id: str
    title: str
    causal_contract: str
    player_agency: str
    setback_law: str
    continuation_policy: str
    checkpoint_interval: int


PLAY_FORMS = (
    PlayForm("platform", "Gravity Stairways",
             "Traverse a grounded side-on course using finite jumps and directional steps",
             "Land beyond the farthest platform without falling into an unguarded hazard",
             "Jump timing, limited endurance and changing surface accessibility",
             "Movement commits to a 1-D step or bounded vertical jump; collisions consume protection",
             ("step", "jump", "brace")),
    PlayForm("puzzle", "Circuit of Contradictions",
             "Toggle physical switches and unlock interdependent logic doors",
             "Satisfy the route's bitwise gate combination without brute-force cheating",
             "Every switch uses scarce energy and rewrites the accessibility pattern",
             "A locked door blocks progression until its exact independent switches align",
             ("toggle", "pass", "inspect")),
    PlayForm("tactics", "Treaty of Moving Fronts",
             "Alternate attack, shield and negotiated withdrawal in finite combat encounters",
             "Resolve the current encounter while conserving protection for later fights",
             "Opponents retaliate after attacks unless shield or parley prevents it",
             "Health, enemy strength and guarded turns form a deterministic encounter clock",
             ("strike", "guard", "parley")),
    PlayForm("survival", "Weatherbound Hearth",
             "Gather survival supplies, build shelter and survive scarce weather cycles",
             "Maintain warmth and hydration through worsening recurring seasons",
             "Unsheltered exposure and thirst cause bounded but real health attrition",
             "Consumables cannot be created by the same operation that consumes them",
             ("drink", "shelter", "scavenge")),
    PlayForm("colony", "Town of Reciprocal Hands",
             "Allocate finite materials between homes, food supply and communal repair",
             "Support a growing colony rather than merely hoard buildings",
             "Population consumes food and unmaintained housing increases risk",
             "Population cannot exceed supported housing and materials are conserved",
             ("construct", "cultivate", "maintain")),
    PlayForm("racing", "Clockless Circuit",
             "Accelerate, brake and negotiate a bounded procedural track",
             "Complete one lap without exhausting vehicle condition",
             "Speed raises impact exposure and braking spends track time",
             "A lap's distance derives from legal motion steps, not free score awards",
             ("accelerate", "brake", "corner")),
    PlayForm("stealth", "The Watching Rooms",
             "Cross spaces using distraction, cover and visible movement",
             "Reach the end of the patrol route below the capture threshold",
             "Every noisy move increments guard suspicion and hiding delays progress",
             "Patrol risk rises from actual movements rather than arbitrary style labels",
             ("sneak", "distract", "hide")),
    PlayForm("commerce", "Exchange of Measured Need",
             "Trade two finite goods according to a changing quoted market price",
             "Sustain positive working capital while fulfilling public demand",
             "Demand shifts market prices; inventory and currency obey conservation",
             "Buy and sell transact against a bounded counterpart inventory",
             ("buy", "sell", "forecast")),
    PlayForm("exploration", "Atlas of Uncertain Paths",
             "Survey unseen sites, navigate existing passages and establish supply caches",
             "Discover enough distinct sites to open a real expedition route",
             "Movement spends endurance; discovery requires physical adjacency",
             "Surveying an already known location never mints fresh discoveries",
             ("explore", "resupply", "chart")),
    PlayForm("rhythm", "Orchestra of Shifting Beats",
             "Perform distinct timed notes against a changing four-beat phrase",
             "Chain accurate timing decisions without skipping failed measures",
             "Off-beat commands break combos and cost energy",
             "The beat sequence advances on every performed note, success or failure",
             ("tap", "hold", "sync")),
)

PROGRESSION_LAWS = (
    ProgressionLaw("chapters", "The Handwritten Chapter",
                   "Complete bounded objectives and preserve a persistent epilogue",
                   "Decide which scarce achievements deserve chapter milestones",
                   "Failure defers progress but preserves prior accomplishments",
                   "postgame", 4),
    ProgressionLaw("endless", "The Unfinishable Horizon",
                   "Objectives recur without a final world victory",
                   "Choose sustainable priorities among inexhaustible opportunities",
                   "Rising environmental pressure punishes unchecked accumulation",
                   "unwinnable", 6),
    ProgressionLaw("roguelite", "The Repeated Expedition",
                   "Each run begins with limited gear; durable knowledge outlasts a failed attempt",
                   "Trade immediate gains against future attempt readiness",
                   "Failed runs reset local score and increase recorded experience",
                   "looping", 5),
    ProgressionLaw("dynasty", "The Generations Agreement",
                   "Each generation inherits finite civic obligations and productive assets",
                   "Invest in long-term welfare rather than one protagonist's lifespan",
                   "Aging transfers unresolved debt rather than deleting it",
                   "persistent", 8),
    ProgressionLaw("factions", "The Unstable Alliance",
                   "Several groups independently gain or lose influence from player actions",
                   "Align, mediate or oppose factions with material consequences",
                   "Unbalanced influence amplifies conflict and limits future negotiation",
                   "branched", 5),
    ProgressionLaw("sandbox", "A World Without Credits",
                   "Build, experiment and recover without an imposed final quest",
                   "Choose self-directed construction and exploration projects",
                   "Material scarcity and cumulative hazards still constrain work",
                   "open", 7),
    ProgressionLaw("mystery", "The Case That Changes",
                   "Collect independent clues and test explanatory hypotheses",
                   "Commit to a theory only after enough verified evidence",
                   "Wrong conclusions increase uncertainty and re-open investigations",
                   "branched", 4),
    ProgressionLaw("seasonal", "Seasons of Shared Scarcity",
                   "Environmental cycles rebalance resources and duties over time",
                   "Time harvests and preparation for different seasons",
                   "Bad preparedness increases exposure every seasonal boundary",
                   "persistent", 4),
    ProgressionLaw("rescue", "The Unending Lifeline",
                   "Travel to help remote communities as crises appear",
                   "Prioritize finite relief across more people than can all be saved",
                   "Unattended needs decay but care remains possible indefinitely",
                   "unwinnable", 3),
    ProgressionLaw("campaign", "The Many-Region Campaign",
                   "A multi-stage goal requires persistent territorial and logistical gains",
                   "Select order of regional interventions and resupply",
                   "Overextension consumes reserve and triggers retreat",
                   "postgame", 6),
    ProgressionLaw("civilization", "The Civic Continuum",
                   "Infrastructure growth unlocks population, trade and obligations",
                   "Develop institutions while retaining public legitimacy",
                   "Neglected obligations reduce long-run prosperity",
                   "persistent", 5),
    ProgressionLaw("branching", "The Roads Not Chosen",
                   "Two mutually exclusive futures remain causally accounted for",
                   "Make irreversible informed commitments while leaving other stories alive",
                   "Wrong turns cannot be erased, only mitigated",
                   "branched", 4),
)

FORM_BY_ID = {form.form_id: form for form in PLAY_FORMS}
ARC_BY_ID = {arc.arc_id: arc for arc in PROGRESSION_LAWS}
if len(FORM_BY_ID) != 10 or len(ARC_BY_ID) != 12:
    raise RuntimeError("original-world gameplay and progression axes must be complete")
if len({x.title.casefold() for x in PLAY_FORMS}) != 10:
    raise RuntimeError("duplicate gameplay-mode authoring")
if len({x.title.casefold() for x in PROGRESSION_LAWS}) != 12:
    raise RuntimeError("duplicate progression-policy authoring")
if any(len(f.mechanics) != 3 or len(set(f.mechanics)) != 3 for f in PLAY_FORMS):
    raise RuntimeError("every play form must define three unique mechanic commands")
