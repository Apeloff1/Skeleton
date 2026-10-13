"""Evidence-based objectives, crises and advice for ten living simulation laws.

Every claim is derived from material facts in a persistent game state.
The director is read-only, never invents resources or certifies a native game,
and never marks unwinnable source worlds globally complete.
"""
from __future__ import annotations
from dataclasses import dataclass

from .original_world_living_10x_runtime import LivingState, validate_living


@dataclass(frozen=True)
class LivingSignal:
    signal_id: str
    title: str
    severity: str
    evidence: str
    suggested_action: str

    def as_dict(self) -> dict:
        return {
            "id": self.signal_id, "title": self.title,
            "severity": self.severity, "evidence": self.evidence,
            "suggested_action": self.suggested_action,
        }


def _conditions(state: LivingState):
    m, world = state.metrics, state.spatial
    kind = validate_living(state).foundation.system.system_id
    if kind == "trophic":
        sustainable = m.vegetation >= m.grazers and m.grazers >= m.predators
        danger = m.vegetation < max(2, m.grazers // 2) or m.grazers == 0
        return sustainable, danger, (
            f"living vegetation={m.vegetation}, grazers={m.grazers}, predators={m.predators}, "
            f"remaining seed bank={m.seedlings}"
        ), ("reseed" if m.vegetation < m.grazers else "protect")
    if kind == "settlement":
        sustainable = m.food >= m.households * 2 and m.unrest <= 3
        danger = m.food < m.households or m.unrest >= 6
        return sustainable, danger, (
            f"households={m.households}/{m.housing}, stored food={m.food}, "
            f"unrest={m.unrest}, arriving households={m.arrivals}"
        ), ("ration" if m.food < 2 * m.households else "house")
    if kind == "caravans":
        sustainable = m.credit >= 10 and m.in_transit == 0
        danger = m.in_transit > 0 and m.escorts == 0
        return sustainable, danger, (
            f"stored goods={m.cargo}, traveling={m.in_transit}, due={m.transit_due}, "
            f"arrived={m.delivered}, credit={m.credit}, escorts={m.escorts}"
        ), ("unload" if m.delivered else ("escort" if m.in_transit else "dispatch"))
    if kind == "watershed":
        sustainable = m.soil >= 7 and m.flood <= 2 and m.reservoir >= 2
        danger = m.flood >= 4 or m.reservoir <= 1
        return sustainable, danger, (
            f"freshwater={m.reservoir}, field health={m.soil}, "
            f"flood damage={m.flood}, engineered dam={m.dam_strength}"
        ), ("release" if m.flood >= 4 else "irrigate")
    if kind == "power":
        sustainable = m.battery >= m.power_demand and m.outages == 0
        danger = m.outages >= 3 or m.grid_wear >= 5 or world.fuel == 0
        return sustainable, danger, (
            f"battery={m.battery}, load={m.power_demand}, fuel={world.fuel}, "
            f"outages={m.outages}, wear={m.grid_wear}"
        ), ("generate" if world.fuel else "charge")
    if kind == "spores":
        sustainable = m.affected <= 1 and m.recovered >= 1
        danger = m.affected > m.unaffected or m.remedies == 0
        return sustainable, danger, (
            f"fictional organisms unaffected={m.unaffected}, affected={m.affected}, "
            f"recovered={m.recovered}, isolated={m.isolation}, remedies={m.remedies}"
        ), ("remedy" if m.affected and m.remedies else "study")
    if kind == "fabrication":
        sustainable = m.completed >= 1 and m.wear < m.builders
        danger = m.wear >= m.builders or m.components < m.orders
        return sustainable, danger, (
            f"builders={m.builders}, wear={m.wear}, parts={m.components}, "
            f"queued builds={m.orders}, finished structures={m.completed}"
        ), ("service" if m.wear else ("design" if not m.orders else "assemble"))
    if kind == "knowledge":
        sustainable = m.shared >= 2 and m.rumors <= 2
        danger = m.rumors > m.shared + m.proven + 4
        return sustainable, danger, (
            f"observations={m.observations}, proven={m.proven}, "
            f"taught={m.shared}, unverified rumors={m.rumors}"
        ), ("teach" if m.proven else ("verify" if m.observations >= 2 else "observe"))
    if kind == "diplomacy":
        sustainable = m.promises == 0 and m.tension <= 3
        danger = m.tension >= 8 or m.goodwill == 0
        return sustainable, danger, (
            f"regional influences={m.faction_a}/{m.faction_b}, tension={m.tension}, "
            f"promises={m.promises}, mediator goodwill={m.goodwill}"
        ), ("mediate" if m.goodwill else "petition")
    sustainable = m.time_debt <= 2 and m.settled_echoes >= 1 and m.queued_echoes == 0
    danger = m.time_debt >= 7 or (m.queued_echoes > 0 and m.chronal_energy == 0)
    return sustainable, danger, (
        f"unpaid historical debt={m.time_debt}, queued echoes={m.queued_echoes}, "
        f"delay={m.echo_delay}, temporal energy={m.chronal_energy}, "
        f"reconciled obligations={m.settled_echoes}"
    ), ("reconcile" if m.time_debt else "record")


def living_objectives(state: LivingState) -> dict:
    law = validate_living(state)
    system = law.foundation.system
    sustainable, dangerous, evidence, recommended = _conditions(state)
    number_of_living_actions = state.events - state.spatial.events
    if number_of_living_actions < 0:
        raise ValueError("living system receipts precede spatial ledger")
    observed = state.living_turns > 0
    intervened = number_of_living_actions > 0
    stabilized = sustainable and observed and intervened
    warnings = []
    if dangerous:
        warnings.append(LivingSignal(
            system.system_id + "-crisis",
            "Real-world-system conservation or stability failure",
            "critical",
            evidence,
            "living " + recommended,
        ).as_dict())
    if state.spatial.danger >= 20:
        warnings.append(LivingSignal(
            "spatial-hazard", "World traversal danger threatens long-term survival",
            "warning", f"persistent danger={state.spatial.danger}",
            "spatial repair",
        ).as_dict())
    goals = [
        {
            "id": "observe-system",
            "title": "Observe one autonomous world-turn consequence",
            "done": observed,
            "proof": f"living turns={state.living_turns}; source tick={state.spatial.tick}",
        },
        {
            "id": "intervene-materially",
            "title": "Pay for a consequential player intervention",
            "done": intervened,
            "proof": f"living intervention receipts={number_of_living_actions}",
        },
        {
            "id": "stabilize-causal-system",
            "title": "Build an actually measurable sustainable outcome",
            "done": stabilized,
            "proof": evidence,
        },
    ]
    continuation = law.source.advanced.arc.continuation_policy
    return {
        "version": "original-living-objective-director.v1",
        "world_id": law.world_id,
        "living_system": system.system_id,
        "architecture": law.source.spatial.architecture.architecture_id,
        "genre": law.source.advanced.mode.form.form_id,
        "continuation": continuation,
        "world_has_guaranteed_win": False,
        "locally_stable": stabilized,
        "source_ending_policy": law.source.advanced.mode.base.ending_policy,
        "warnings": warnings,
        "objectives": goals,
        "next_action": "living " + recommended,
        "no_native_game_claim": True,
        "worlds_are_composed_not_individually_written": True,
    }
