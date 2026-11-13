"""Targeted, source-bound acceptance witnesses for real original NPC games.

Unlike a random stress test, this explicitly tries to PROVE one ticketed
transit and one trust-gated transit from a clean initial character. Every
used command is a legal DirectorAction and each resulting history is replayed
from genesis in a second independent pass. Failure is a counterexample or an
unproven path, not a falsely passing game or certificate.

Read-only: no sessions, sources, training checkpoints or Godot files change.
Bounded searches limit this invocation, not playthrough time or game size.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, director_initial, director_step, available_director_actions,
)
from skeleton.ai.game_builder.quest_society import (
    phase, residents_here, verify_inventory,
)
from skeleton.ai.game_builder.quest_campaign_completion import (
    _dynamic_path, CampaignCompletionError,
)
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.society_acceptance.v1"
MAX_STEPS = 240
MAX_PROBES = 8


def _hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


class _Trace:
    def __init__(self, world: Any) -> None:
        self.world = world
        self.state = director_initial(world)
        self.initial_sha = self.state.digest
        self.actions: list[dict[str, Any]] = []
        self.earned_trust: Counter[str] = Counter()
        self.redeemed: Counter[str] = Counter()
        self.merchandise_bought = Counter()
        self.transits = Counter()
        self.calendar_periods = Counter()
        self.world_flags = Counter()
        self.starting_wallet = self.state.world_state.society.balance

    def do(self, action: DirectorAction) -> None:
        if len(self.actions) >= MAX_STEPS:
            raise CampaignCompletionError(
                "NPC acceptance action witness exceeded one probe's search budget"
            )
        before = self.state
        if action not in available_director_actions(self.world, before):
            raise CampaignCompletionError(
                "NPC acceptance action was not currently playable"
            )
        before_social = before.world_state.society
        verify_inventory(self.world.dynamics.society, before.acquired, before_social)
        now = director_step(self.world, before, action)
        after_social = now.world_state.society
        verify_inventory(self.world.dynamics.society, now.acquired, after_social)
        if now.turn <= before.turn:
            raise ValueError("original world interaction failed to advance game clock")
        self.calendar_periods[phase(self.world.dynamics.society, before.turn)["phase"]] += 1
        if action.kind == "buy":
            self.merchandise_bought[action.key] += 1
        if action.kind == "transit":
            self.transits[action.key] += 1
        before_trust = dict(before_social.relationships)
        for npc, value in after_social.relationships:
            if value > before_trust[npc]:
                self.earned_trust[npc] += value - before_trust[npc]
        spent_before = dict(before_social.consumed_goods)
        for good, count in after_social.consumed_goods:
            added = count - spent_before.get(good, 0)
            if added < 0:
                raise ValueError("NPC society redemption ledger moved backwards")
            if added:
                self.redeemed[good] += added
        for flag in set(now.world_state.world_flags) - set(
                before.world_state.world_flags):
            self.world_flags[flag] += 1
        item = {
            "before": before.digest, "action": action.payload(),
            "after": now.digest,
        }
        self.actions.append(item)
        self.state = now

    def follow(self, actions: tuple[DirectorAction, ...]) -> None:
        for action in actions:
            self.do(action)

    def replay(self) -> dict[str, Any]:
        fresh = director_initial(self.world)
        digest = _hash({"initial": fresh.digest, "world": self.world.digest})
        for recorded in self.actions:
            if fresh.digest != recorded["before"]:
                raise ValueError("NPC acceptance history is not a coherent legal chain")
            action = DirectorAction(**recorded["action"])
            if action not in available_director_actions(self.world, fresh):
                raise ValueError("NPC acceptance journal tried to invent an available action")
            fresh = director_step(self.world, fresh, action)
            if fresh.digest != recorded["after"]:
                raise ValueError("NPC acceptance result changed on independent replay")
            verify_inventory(self.world.dynamics.society, fresh.acquired,
                             fresh.world_state.society)
            digest = _hash({"parent": digest, "receipt": recorded})
        if fresh != self.state:
            raise ValueError("NPC acceptance did not reproduce its final game world")
        return {
            "actions_replayed": len(self.actions),
            "initial_state_sha256": self.initial_sha,
            "final_state_sha256": fresh.digest,
            "rolling_witness_sha256": digest,
            "source_legal_actions_replayed_twice": True,
            "coins_initial": self.starting_wallet,
            "coins_after": fresh.world_state.society.balance,
            "goods_bought": dict(sorted(self.merchandise_bought.items())),
            "goods_redeemed": dict(sorted(self.redeemed.items())),
            "NPC_trust_gained": dict(sorted(self.earned_trust.items())),
            "game_phase_actions": dict(sorted(self.calendar_periods.items())),
            "transport_routes_taken": dict(sorted(self.transits.items())),
            "new_world_events": dict(sorted(self.world_flags.items())),
            "ending_scene": fresh.scene,
            "ending_turn": fresh.turn,
            "final_social_state": fresh.world_state.society.payload(),
            "native_3D_or_2D_game_playthrough_proven": False,
        }


def _ticket(world: Any, passage: Any) -> dict[str, Any]:
    progress = _Trace(world)
    product = passage.consume_item
    if product is None:
        raise CampaignCompletionError("ticket scenario is missing a real resource fare")
    # All steps, including shopping, are proposed through the same canonical
    # permission state that ordinary players see.
    progress.follow(_dynamic_path(
        world, progress.state, passage.source, required_item=product,
    ))
    if progress.state.scene != passage.source or product not in progress.state.acquired:
        raise CampaignCompletionError("market ticket could not be earned at transit origin")
    old_uses = dict(progress.state.world_state.passage_uses).get(passage.key, 0)
    old_spent = dict(progress.state.world_state.society.consumed_goods).get(product, 0)
    progress.do(DirectorAction("transit", passage.key, progress.state.scene))
    now = progress.state
    used = dict(now.world_state.passage_uses).get(passage.key, 0)
    spent = dict(now.world_state.society.consumed_goods).get(product, 0)
    if (used - old_uses != 1 or spent - old_spent != 1
            or now.scene != passage.destination):
        raise ValueError("ticketed ferry did not actually redeem one shop resource")
    report = progress.replay()
    report.update({
        "scenario": "source_verified_ticket_transport",
        "fare_good": product, "fare_quantity_spent": 1,
        "destination": passage.destination,
    })
    return report


def _trust(world: Any, passage: Any) -> dict[str, Any]:
    requirement = passage.requirements.trust[0]
    rules = world.dynamics.society
    npc = next(n for n in rules.residents if n.key == requirement.resident)
    if npc.initial_trust > requirement.at_most:
        raise CampaignCompletionError("NPC already beyond maximum acceptable standing")
    progress = _Trace(world)
    for attempt in range(MAX_STEPS - 1):
        at = progress.state
        if (at.scene == passage.source
                and DirectorAction("transit", passage.key, at.scene)
                    in available_director_actions(world, at)):
            break
        trust = dict(at.world_state.society.relationships)[npc.key]
        present = {n.key for n in residents_here(rules, at.scene, at.turn)}
        if trust < requirement.at_least and npc.key in present:
            options = [
                action for action in available_director_actions(world, at)
                if ((action.kind == "speak" and action.key == npc.key)
                    or (action.kind == "discuss"
                        and any(npc.key + "_" + choice.key == action.key
                                for choice in npc.dialogue)))
            ]
            ranking = []
            for action in options:
                if action.kind == "speak":
                    gain = npc.trust_gain
                else:
                    choice = next(choice for choice in npc.dialogue
                                  if npc.key + "_" + choice.key == action.key)
                    gain = choice.trust_delta
                if gain > 0:
                    ranking.append((-gain, action.key, action))
            if ranking:
                ranking.sort(key=lambda row: (row[0], row[1]))
                progress.do(ranking[0][2])
                continue
        if at.scene != passage.source and trust >= requirement.at_least:
            progress.follow(_dynamic_path(world, at, passage.source))
            continue
        if at.scene not in npc.schedule and trust < requirement.at_least:
            target = npc.schedule[phase(rules, at.turn)["phase_index"]]
            progress.follow(_dynamic_path(world, at, target))
            continue
        if at.scene != npc.schedule[phase(rules, at.turn)["phase_index"]] and (
                trust < requirement.at_least):
            target = npc.schedule[phase(rules, at.turn)["phase_index"]]
            progress.follow(_dynamic_path(world, at, target))
            continue
        progress.do(DirectorAction("rest", "rest", at.scene))
    else:
        raise CampaignCompletionError("trust scenario did not prove an actual open route")
    old_scene = progress.state.scene
    progress.do(DirectorAction("transit", passage.key, old_scene))
    if progress.state.scene != passage.destination:
        raise ValueError("trusted guide failed to deliver actual authored transport")
    report = progress.replay()
    report.update({
        "scenario": "source_verified_trust_transport",
        "NPC": npc.key, "required_min_trust": requirement.at_least,
        "actual_final_trust": dict(progress.state.world_state.society.relationships)[npc.key],
        "destination": passage.destination,
    })
    return report


def prove(root: Path, *, source: str) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    world, source_sha = _load_world(root, source)
    if world.dynamics is None or world.dynamics.society is None:
        raise ValueError("NPC acceptance needs a reviewed original-society campaign")
    passages = tuple(world.dynamics.passages)
    ticket = next(
        (route for route in passages
         if route.consume_item is not None
         and any(route.consume_item == good.key
                 for shop in world.dynamics.society.shops for good in shop.goods)), None,
    )
    trusting = next((route for route in passages if route.requirements.trust), None)
    results = []
    attempted = []
    for label, route, method in (
            ("ticket", ticket, _ticket),
            ("trust", trusting, _trust)):
        if route is None:
            attempted.append({
                "scenario": label, "status": "not_authored",
                "verified": False, "not_a_failure": True,
            })
            continue
        try:
            result = method(world, route)
            result["verified"] = True
            results.append(result)
            attempted.append({
                "scenario": label, "status": "verified",
                "verified": True,
                "ending_sha256": result["final_state_sha256"],
            })
        except (ValueError, TypeError, KeyError, CampaignCompletionError) as error:
            attempted.append({
                "scenario": label, "status": "failed_or_unproven",
                "verified": False,
                "error_type": type(error).__name__,
                "reason": str(error)[:350],
            })
    if _read(root, source, 16 * 1024 * 1024)[1] != source_sha:
        raise ValueError("game source changed during NPC acceptance verification")
    authored = sum(row["status"] != "not_authored" for row in attempted)
    verified = sum(row["verified"] for row in attempted)
    return {
        "ok": authored == verified and authored > 0,
        "schema": SCHEMA, "action": "director-society-acceptance",
        "project": world.project_id,
        "source_sha256": source_sha, "world_sha256": world.digest,
        "authored_witness_scenarios": authored,
        "accepted_scenarios": verified,
        "scenario_results": attempted, "verified_witnesses": results,
        "no_gameplay_sessions_or_files_mutated": True,
        "no_automatic_model_training": True,
        "no_native_godot_full_playthrough_verified": True,
        "first_install_behavior_unverified": True,
        "professional_character_voice_review_required": True,
    }
