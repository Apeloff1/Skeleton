"""Deep dynamic-world access, reputation, gate and transit scrutiny.

Unlike static topology audits, every initially offered traversal is evaluated
using real Director initial state. Reports are diagnostics, not proofs that all
future faction permutations are reachable, or that the writing is compelling.
No user save is opened or mutated by this source-only world inspection.
"""
from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, available_director_actions, director_initial, director_step,
)
from skeleton.ai.game_builder.quest_world_dynamics import (
    WorldDynamics, Requirements, permits, initial as initial_world_state,
)
from skeleton.developer.jeeves_game_production_board import _load_world
from skeleton.developer.jeeves_game_director_session import _hash

SCHEMA = "skeleton.jeeves.dynamic_world_assurance.v1"


def _directed_graph(world: Any, *, blocked: set[tuple[str, str]]
                    ) -> dict[str, set[str]]:
    return {
        s.key: {link for link in s.links if (s.key, link) not in blocked}
        for s in world.scenes
    }


def _reachable(graph: dict[str, set[str]], start: str) -> set[str]:
    found, pending = set(), deque([start])
    while pending:
        node = pending.popleft()
        if node in found:
            continue
        found.add(node)
        pending.extend(graph[node] - found)
    return found


def _requirement_summary(requirements: Requirements) -> dict[str, Any]:
    return {
        "required_items": list(requirements.items),
        "required_quest_flags": list(requirements.flags),
        "required_completed_quests": list(requirements.quests),
        "required_world_flags": list(requirements.world_flags),
        "forbidden_outcome_flags": list(requirements.forbidden_flags),
        "forbidden_world_flags": list(requirements.forbidden_world_flags),
        "reputation_thresholds": [x.payload() for x in requirements.standings],
        "requires_material_progress": bool(
            requirements.items or requirements.flags or requirements.quests
            or requirements.world_flags or requirements.standings
        ),
    }


def _producers(world: Any) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for scene in world.scenes:
        for affordance in scene.affordances:
            if affordance.produces:
                result.setdefault(affordance.produces, []).append(
                    scene.key + ":" + affordance.key
                )
    return {key: sorted(set(x)) for key, x in sorted(result.items())}


def _quest_outcomes(world: Any) -> dict[str, list[str]]:
    return {
        q.key: sorted({x.outcome_flag for stage in q.stages
                       for x in stage.solutions})
        for q in world.quests
    }


def _flag_producers(dynamics: WorldDynamics) -> dict[str, list[str]]:
    producers = {}
    for effect in dynamics.influences:
        if effect.grant_world_flag:
            producers.setdefault(effect.grant_world_flag, []).append(
                "influence:" + effect.key
            )
    for passage in dynamics.passages:
        if passage.grant_world_flag:
            producers.setdefault(passage.grant_world_flag, []).append(
                "passage:" + passage.key
            )
    return {k: sorted(v) for k, v in sorted(producers.items())}


def _standing_ranges(dynamics: WorldDynamics) -> dict[str, dict[str, Any]]:
    ranges = {}
    for faction in dynamics.factions:
        effects = [x.delta for x in dynamics.influences if x.faction == faction.key]
        transport_effects = [
            n for route in dynamics.passages for f, n in route.reputation_change
            if f == faction.key
        ]
        changes = effects + transport_effects
        ranges[faction.key] = {
            "starting_standing": faction.starting_standing,
            "positive_effects_declared": sum(x > 0 for x in changes),
            "negative_effects_declared": sum(x < 0 for x in changes),
            "max_positive_single_event": max([0, *changes]),
            "min_negative_single_event": min([0, *changes]),
            "no_reputation_gain_authored": not any(x > 0 for x in changes),
            "unbounded_repeat_effects_possible": any(
                r.faction == faction.key and not r.once
                for r in dynamics.influences
            ) or any(f == faction.key and delta > 0
                     for p in dynamics.passages
                     for f, delta in p.reputation_change),
        }
    return ranges


def _record_deadlocks(world: Any, dynamics: WorldDynamics,
                      initial: Any) -> list[dict[str, Any]]:
    """Conservative *possible* deadlocks, not a false reachability proof."""
    from skeleton.ai.game_builder.quest_world_dynamics import gate_for
    blocked = {
        (gate.source, gate.destination)
        for gate in dynamics.gates if not permits(gate.requirements, initial)
    }
    normal_graph = _directed_graph(world, blocked=blocked)
    # Open authored transit edges make the starting graph richer.
    for route in dynamics.passages:
        if not permits(route.requirements, initial):
            continue
        normal_graph[route.source].add(route.destination)
        if route.bidirectional:
            normal_graph[route.destination].add(route.source)
    reachable = _reachable(normal_graph, world.starting_scene)
    gaps = []
    for quest in world.quests:
        for stage in quest.stages:
            target = set(stage.scene_ids)
            if not (target & reachable):
                gaps.append({
                    "kind": "currently_inaccessible_quest_stage",
                    "quest": quest.key, "stage": stage.key,
                    "locations": sorted(target),
                    "reason": "No currently legal initial-world route; later world events may unlock access",
                    "permanent_unreachability_proven": False,
                })
    for source in sorted(normal_graph):
        returns = _reachable(normal_graph, source)
        if world.starting_scene not in returns:
            gaps.append({
                "kind": "possible_no_return_zone", "scene": source,
                "reason": "Current permissions cannot lead back to opening world",
                "permanent_unreachability_proven": False,
            })
    return gaps


def analyze(world: Any) -> dict[str, Any]:
    if world.dynamics is None:
        raise ValueError("reviewed world has no dynamic transit/reputation configuration")
    d = world.dynamics
    current = director_initial(world)
    productions = _producers(world)
    outcomes = _quest_outcomes(world)
    world_flags = _flag_producers(d)
    reputation = _standing_ranges(d)
    gate_checks = []
    for gate in d.gates:
        permit = permits(gate.requirements, current)
        gate_checks.append({
            "source": gate.source, "destination": gate.destination,
            "label": gate.label, "initially_open": permit,
            "requirements": _requirement_summary(gate.requirements),
        })
    passage_checks = []
    for route in d.passages:
        permit = permits(route.requirements, current)
        passage_checks.append({
            "key": route.key, "source": route.source,
            "destination": route.destination, "mode": route.mode,
            "cost_turns": route.cost_turns, "initially_open": permit,
            "bidirectional": route.bidirectional,
            "consumes_ticket": route.consume_item is not None,
            "ticket": route.consume_item,
            "reputation_change": [list(x) for x in route.reputation_change],
            "requirements": _requirement_summary(route.requirements),
        })
    issues = []
    # The explicit configured world may still have deadlocks at particular
    # story stages; never call static reachability a complete proof.
    for deadlock in _record_deadlocks(world, d, current):
        issues.append({"severity": "review", **deadlock})
    for effect in d.influences:
        if effect.delta == 0 and effect.grant_world_flag is None:
            issues.append({
                "severity": "review", "kind": "inert_faction_effect",
                "influence": effect.key,
                "reason": "No faction delta or world flag is produced",
            })
    for route in d.passages:
        if (route.consume_item is not None
                and len(productions.get(route.consume_item, [])) == 1):
            issues.append({
                "severity": "review", "kind": "unique_ticket_consumption",
                "passage": route.key, "ticket": route.consume_item,
                "reason": "A single authored producer may create an irreversible fare softlock",
            })
        if route.bidirectional and route.grant_world_flag is not None:
            issues.append({
                "severity": "review", "kind": "repeatable_world_event",
                "passage": route.key,
                "reason": "Round trips can repeatedly trigger this route; world flag stays monotonic",
            })
    # A guarded walking edge with an alternate static ungated path is
    # intentionally a puzzle, not a global softlock.
    blocked_normal = {(g.source, g.destination) for g in d.gates}
    ungated = _directed_graph(world, blocked=blocked_normal)
    for gate in d.gates:
        bypass = gate.destination in _reachable(ungated, gate.source)
        if not bypass:
            issues.append({
                "severity": "review", "kind": "gate_without_static_foot_bypass",
                "source": gate.source, "destination": gate.destination,
                "reason": "Entry must be unlocked or use another transport; verify full campaign progression",
            })
    static_regions = sorted({s.region for s in world.scenes})
    data = {
        "schema": SCHEMA, "project": world.project_id,
        "world_sha256": world.digest,
        "faction_count": len(d.factions),
        "walking_gate_count": len(d.gates),
        "transport_count": len(d.passages),
        "authored_influence_count": len(d.influences),
        "regions": static_regions,
        "initial_standings": dict(current.world_state.standings),
        "material_item_producers": productions,
        "authored_quest_outcomes": outcomes,
        "authored_world_flag_producers": world_flags,
        "faction_influence_summary": reputation,
        "walking_gates": gate_checks,
        "transit_passages": passage_checks,
        "structural_risks": issues,
        "risk_count": len(issues),
        "native_transport_animation_verified": False,
        "complete_dynamic_state_space_exhaustively_proven": False,
        "original_game_quality_independently_approved": False,
        "production_checkpoint_trained": False,
    }
    data["assurance_sha256"] = _hash(data)
    return data


def audit(root: Path, *, source: str) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    world, source_sha = _load_world(root, source)
    details = analyze(world)
    if _read(root, source, 16 * 1024 * 1024)[1] != source_sha:
        raise ValueError("reviewed game source changed during dynamic-world audit")
    return {
        "ok": True, "action": "director-dynamics-audit",
        "source": source, "source_sha256": source_sha,
        "analysis": details, "source_bound": True,
        "signoff_produced": False, "gameplay_modified": False,
    }
