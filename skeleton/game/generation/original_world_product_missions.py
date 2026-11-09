"""Story/mission proof director for the 16 original causal domains.

This director binds each individually written root world's invariant, player
lever, failure mode, consequence regime and ending policy to measurable
physical play. It supplies actionable checks; it does NOT pretend that
each of the 1,424 root premises has a bespoke script, dialogue tree, or
verified production-quality realization. Every progress claim has a precise
state-derived witness; no free quest rewards or invented completed games.
"""
from __future__ import annotations
from dataclasses import dataclass

from .original_foundation_compiler import FoundationError, REGIME_COUNT
from .original_world_product_session import ProductSession, validate_product
from .original_world_product_terrain import _base_cell

MISSION_VERSION = "original-root-evidence-director.v1"

DOMAIN_EVIDENCE = {
    "geometry": ("Build or anchor a traversable physical connection",
                 "bridge/construction score", "spatial bridge"),
    "chronology": ("Advance recorded world time and settle delayed commitments",
                   "world clock and causal echo", "causal intervene"),
    "ecosphere": ("Produce measurable habitat or ecological recovery",
                  "regenerative ecosystem reserves", "living reseed"),
    "materials": ("Extract finite terrain resources and construct with them",
                  "physically depleted geological resource sites", "terrain mine"),
    "governance": ("Legitimately exercise and reconcile public authority",
                   "civic trust, accepted authority and public action", "causal intervene"),
    "community": ("Develop durable supportive resident relationships",
                  "inhabitant trust and social support", "studio gift"),
    "commerce": ("Complete physical trade and maintain credible value",
                 "real stores, earned credits and delivered goods", "living dispatch"),
    "memory": ("Collect independently verified evidence of the changing world",
               "source evidence and recorded investigated sites", "causal study"),
    "language": ("Disseminate a tested message or interpretation",
                 "source evidence and shared public knowledge", "living verify"),
    "metaphysics": ("Pay for a consensual original-world ritual or myth mechanism",
                    "root intervention and tangible offered reserves", "causal intervene"),
    "navigation": ("Reach and map actual adjacent locations",
                   "spatial survey and physically visited terrain", "spatial travel"),
    "discovery": ("Investigate unseen sites and prove independent knowledge",
                  "explored sites, living evidence and discoveries", "causal survey"),
    "simulation": ("Maintain a verified operating machine under scarce resources",
                   "persistent robotic building and intervention", "living design"),
    "craft": ("Finish physical built objects from gathered finite materials",
              "constructed terrain and world workshop projects", "terrain build_hearth"),
    "affection": ("Grow lasting relationships through consensual care",
                 "named resident relationships and trust", "studio gift"),
    "survival": ("Sustain shelter, provisions and finite living energy",
                 "safe shelter, available food and source stamina", "terrain build_hearth"),
}

REGIME_EVIDENCE = {
    "echo": ("Recognize a deferred causal obligation", "echo_due"),
    "levy": ("Account for resources transferred to public reserve", "reserve"),
    "reverse": ("Observe consequences of a reversible intervention", "remote"),
    "threshold": ("Cross and verify a consequential threshold", "milestones"),
    "migration": ("Trace effects appearing in another region", "remote"),
    "veto": ("Exercise social consent before a contested action", "trust"),
    "cascade": ("Inspect accumulated causal momentum", "momentum"),
    "exchange": ("Account for resources in two finite ledgers", "reserve"),
    "auction": ("Resolve a priced or contested resource", "duty"),
    "fork": ("Record one irreversible original-world choice", "branch"),
}
assert len(DOMAIN_EVIDENCE) == 16
assert len(REGIME_EVIDENCE) == 10


@dataclass(frozen=True)
class MissionProof:
    id: str
    title: str
    instruction: str
    current: int
    required: int
    verified: bool
    witness: str
    unlock: bool

    def as_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title,
            "instruction": self.instruction,
            "current": self.current,
            "required": self.required,
            "verified": self.verified,
            "witness": self.witness,
            "unlock": self.unlock,
        }


def _domain_progress(session: ProductSession, domain: str) -> int:
    local, world = session.terrain, session.living
    m, source = world.metrics, world.spatial.game.causal
    physical = world.spatial
    person = session.society.inhabitants
    if domain == "geometry":
        return sum(1 for t in local.edits if t.bridge) + (
            physical.roadways + physical.splices + physical.anchors
            + physical.ferries + physical.braces + physical.tethers
            + physical.alignment + physical.attunement
            + physical.stability + physical.seals
        )
    if domain == "chronology":
        return min(world.living_turns, 2) + min(source.echo_due, 2)
    if domain == "ecosphere":
        return min(m.habitat - 8, 5) if m.habitat >= 8 else 0
    if domain == "materials":
        return sum(
            _base_cell(local.design_id, local.biome, edit.x, edit.y).stone
            - edit.stone for edit in local.edits
        )
    if domain == "governance":
        return min(3, source.primary // 2)
    if domain == "community":
        return max(0, max(p.relationships for p in person) - 4)
    if domain == "commerce":
        return max(0, m.credit - 8) // 2 + int(m.delivered > 0)
    if domain == "memory":
        return max(0, source.evidence - 2)
    if domain == "language":
        return max(0, m.shared + source.evidence - 2)
    if domain == "metaphysics":
        return min(3, source.primary // 2)
    if domain == "navigation":
        return max(0, len(physical.visited) - 1) + max(
            0, sum(e.visits for e in local.edits))
    if domain == "discovery":
        return max(0, len(source.investigated) - 1) + sum(
            p.discoveries for p in person)
    if domain == "simulation":
        return m.completed + min(2, source.primary)
    if domain == "craft":
        return sum(bool(t.building) for t in local.edits) + m.completed
    if domain == "affection":
        return max(0, max(p.relationships for p in person) - 4)
    if domain == "survival":
        return local.shelter + int(
            local.provisions >= 5 and world.living_turns >= 2)
    raise FoundationError("unknown authored domain")


def _overlay_progress(session: ProductSession, op: str) -> int:
    source = session.living.spatial.game.causal
    if op == "fork":
        return int(bool(source.branch))
    if op == "veto":
        return int(source.event_count >= 1 and source.trust >= 5)
    if op in ("levy", "exchange"):
        return max(0, source.reserve - 6)
    if op == "auction":
        return source.duty
    return getattr(source, REGIME_EVIDENCE[op][1])


def mission_report(session: ProductSession) -> dict:
    law = validate_product(session)
    foundation = law.source.advanced.mode.base
    domain, op = foundation.domain, foundation.regime.operator
    if domain not in DOMAIN_EVIDENCE or op not in REGIME_EVIDENCE:
        raise FoundationError("unsupported authored mission causal law")
    description, witness, suggestion = DOMAIN_EVIDENCE[domain]
    outcome, field = REGIME_EVIDENCE[op]
    variant = foundation.foundation_index // REGIME_COUNT % 8
    difficulty = 1 + variant // 3
    physical = _domain_progress(session, domain)
    overlay = _overlay_progress(session, op)
    source = session.living.spatial.game.causal
    activated = source.primary >= 1 and source.event_count > 0
    progress = [
        MissionProof(
            "foundation", foundation.root.title,
            foundation.root.invariant + ". " + description
            + ". Player agency: " + foundation.root.lever,
            min(physical, difficulty), difficulty, physical >= difficulty,
            witness, True,
        ),
        MissionProof(
            "consequence", foundation.regime.title,
            outcome + ". " + foundation.coupling + ". "
            + foundation.regime.failure,
            min(overlay, 1), 1, overlay >= 1,
            field, physical >= difficulty,
        ),
        MissionProof(
            "resolution", "Advance the original world's causal history",
            foundation.failure_pressure + ". " + foundation.ending_policy,
            int(activated and session.living.living_turns >= 1), 1,
            activated and session.living.living_turns >= 1,
            "Actual source causal action, authored root player lever and a completed world turn",
            physical >= difficulty and overlay >= 1,
        ),
    ]
    return {
        "schema": MISSION_VERSION,
        "world_id": law.world_id,
        "authored_root_id": foundation.root.root_id,
        "authored_premise": foundation.root.invariant,
        "authored_lever": foundation.root.lever,
        "authored_failure": foundation.root.failure,
        "authorial_ending_policy": foundation.root.ending_policy,
        "regime_id": foundation.regime.regime_id,
        "domain": domain,
        "domain_actions": suggestion,
        "root_variant": variant,
        "difficulty": difficulty,
        "missions": [p.as_dict() for p in progress],
        "verified_local_milestones": sum(p.verified for p in progress),
        "global_victory_certified": False,
        "bespoke_world_mechanic_fully_implemented": False,
        "explicit_limitation": (
            "These 16 domain and 10 regime proof patterns expose real gameplay evidence, "
            "but each fictional handwritten root still needs its own bespoke physics "
            "and authored narrative production."
        ),
    }
