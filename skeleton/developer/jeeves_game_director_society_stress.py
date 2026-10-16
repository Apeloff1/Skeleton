"""Adversarial NPC-market and calendar simulation, not a fake game playthrough.

Each scenario performs real canonical Director actions entirely in memory,
then replays them again. The game source and any actual player session remain
untouched. Bounded per-scenario probe windows are not a lifetime game step,
AI inference time, model training, authoring or recording limit.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, available_director_actions, director_initial, director_step,
)
from skeleton.ai.game_builder.quest_society import phase, verify_inventory
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.original_society_adversarial.v1"
PROFILES = (
    "market_roundtrip", "relationship_builder", "skeptical_dialogue",
    "traveler", "liquidity_pressure", "calendar_sweep",
    "deterministic_mixed", "world_unlock",
)


def _hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _pick(choices: tuple[DirectorAction, ...], *, profile: int,
          sequence: int, scene: str, world_hash: str) -> DirectorAction:
    if not choices:
        raise ValueError("original game ceased to offer any legal gameplay actions")
    def score(action: DirectorAction) -> tuple[int, str, str]:
        category = action.kind
        if profile == 0:
            preference = {
                "buy": 0, "sell": 1, "speak": 3, "discuss": 4,
                "rest": 5, "transit": 6, "travel": 7, "wait": 8, "use": 9,
            }
        elif profile == 1:
            preference = {
                "discuss": 0, "speak": 1, "rest": 2, "buy": 3,
                "travel": 4, "transit": 5, "sell": 6, "use": 7, "wait": 8,
            }
        elif profile == 2:
            preference = {
                "discuss": 0, "speak": 1, "rest": 2, "sell": 3,
                "travel": 4, "transit": 5, "buy": 6, "use": 7, "wait": 8,
            }
        elif profile == 3:
            preference = {
                "transit": 0, "travel": 1, "discuss": 2, "buy": 3,
                "speak": 4, "rest": 5, "sell": 6, "use": 7, "wait": 8,
            }
        elif profile == 4:
            preference = {
                "sell": 0, "buy": 1, "rest": 2, "discuss": 3,
                "speak": 4, "travel": 5, "transit": 6, "wait": 7, "use": 8,
            }
        elif profile == 5:
            preference = {
                "rest": 0, "wait": 1, "speak": 2, "discuss": 3,
                "buy": 4, "sell": 5, "travel": 6, "transit": 7, "use": 8,
            }
        else:
            seed = _hash({
                "world": world_hash, "profile": profile,
                "sequence": sequence, "scene": scene,
                "action": action.payload(),
            })
            # Uniformly deterministic selection by hashed action identity,
            # without depending on global RNG, web APIs or machine clock.
            return int(seed[:12], 16), category, action.key
        if profile == 2 and category == "discuss":
            # Critically examine negative dialogue consequences, not only
            # the positive-rapport branch selected by ordinary sorting.
            return (preference[category],
                    "0" if "question_motives" in action.key else "1",
                    action.key)
        return preference.get(category, 99), category, action.key

    return min(choices, key=score)


def _probe(world: Any, *, index: int, steps: int) -> dict[str, Any]:
    rules = world.dynamics.society
    before = director_initial(world)
    now = before
    verify_inventory(rules, before.acquired, before.world_state.society)
    turns = 0
    actions = []
    spent = 0
    received = 0
    shop_counter: Counter[str] = Counter()
    talk_counter: Counter[str] = Counter()
    phase_hits: Counter[str] = Counter()
    world_unlocks = {}
    first_passages = {}
    all_action_digest = _hash({
        "initial": before.digest, "scenario": index, "world": world.digest,
    })
    for sequence in range(1, steps + 1):
        choices = available_director_actions(world, now)
        chosen = _pick(
            choices, profile=index, sequence=sequence,
            scene=now.scene, world_hash=world.digest,
        )
        prior = now
        previous_social = prior.world_state.society
        period = phase(rules, prior.turn)
        now = director_step(world, now, chosen)
        later_social = now.world_state.society
        if later_social is None:
            raise ValueError("NPC economy vanished during adversarial replay")
        verify_inventory(rules, now.acquired, later_social)
        phase_hits[period["phase"]] += 1
        turns += now.turn - prior.turn
        money_delta = later_social.balance - previous_social.balance
        spent += max(0, -money_delta)
        received += max(0, money_delta)
        if chosen.kind in {"buy", "sell"}:
            shop_counter[chosen.kind + ":" + chosen.key] += 1
        if chosen.kind in {"discuss", "speak"}:
            talk_counter[chosen.key] += 1
        if chosen.kind == "transit":
            first_passages.setdefault(chosen.key, sequence)
        if not set(prior.world_state.world_flags).issubset(
                now.world_state.world_flags):
            raise ValueError("world-event flag disappeared in social stress run")
        for flag in set(now.world_state.world_flags) - set(
                prior.world_state.world_flags):
            world_unlocks.setdefault(flag, sequence)
        if later_social.balance != (
                before.world_state.society.balance - spent + received):
            raise ValueError("NPC market broke exact monetary conservation")
        if now.turn < prior.turn:
            raise ValueError("world clock traveled backwards")
        witness = {
            "choice": chosen.payload(), "before": prior.digest,
            "after": now.digest,
        }
        all_action_digest = _hash({
            "prior_sha256": all_action_digest,
            "action_receipt": witness,
        })
        actions.append(witness)
    # Independent second playthrough; do not borrow the first run's internal
    # states, progression objects, faction standing or wallet contents.
    reloaded = director_initial(world)
    second_digest = _hash({
        "initial": reloaded.digest, "scenario": index, "world": world.digest,
    })
    for witness in actions:
        action = DirectorAction(**witness["choice"])
        if action not in available_director_actions(world, reloaded):
            raise ValueError("NPC playthrough action was legal only on the first run")
        if witness["before"] != reloaded.digest:
            raise ValueError("NPC replay predecessor hash differs")
        reloaded = director_step(world, reloaded, action)
        if witness["after"] != reloaded.digest:
            raise ValueError("NPC replay result differs from canonical state")
        second_digest = _hash({
            "prior_sha256": second_digest, "action_receipt": witness,
        })
    if now != reloaded or all_action_digest != second_digest:
        raise ValueError("NPC stress state/history differs after independent replay")
    beginning = before.world_state.society
    ending = now.world_state.society
    if ending.balance != beginning.balance + received - spent:
        raise ValueError("NPC economy lost or fabricated original-game currency")
    verify_inventory(rules, now.acquired, ending)
    # Original market has no free money creation, and price rules prohibit
    # arbitrage. A higher final wallet would be a real economic exploit.
    if ending.balance > beginning.balance:
        raise ValueError("positive-money exploit in finite NPC market")
    stock_start = {(shop, item): count
                   for shop, item, count in beginning.shop_stock}
    stock_end = {(shop, item): count
                 for shop, item, count in ending.shop_stock}
    inventory = dict(ending.owned)
    for item, quantity in inventory.items():
        if quantity < 1:
            raise ValueError("market inventory contains a non-positive stack")
    return {
        "profile": PROFILES[index],
        "scenario": index, "actions_executed": steps,
        "turns_simulated": turns,
        "initial_state_sha256": before.digest,
        "final_state_sha256": now.digest,
        "rolling_action_receipt_sha256": all_action_digest,
        "independent_replay_matches": True,
        "initial_wallet": beginning.balance,
        "final_wallet": ending.balance,
        "coins_spent": spent,
        "coins_received": received,
        "NPC_interactions": dict(sorted(talk_counter.items())),
        "market_actions": dict(sorted(shop_counter.items())),
        "calendar_period_exposure": dict(sorted(phase_hits.items())),
        "faction_standings": dict(now.world_state.standings),
        "final_NPC_trust": dict(ending.relationships),
        "acquired_world_events": dict(sorted(world_unlocks.items())),
        "first_observed_transport_uses": dict(sorted(first_passages.items())),
        "merchant_stock_changes": [
            {"shop": shop, "good": item,
             "before": stock_start[(shop, item)],
             "after": stock_end[(shop, item)]}
            for shop, item in sorted(stock_end)
            if stock_start[(shop, item)] != stock_end[(shop, item)]
        ],
        "final_player_commerce_goods": [list(x) for x in ending.owned],
        "irreversibly_used_merchandise": [list(x) for x in ending.consumed_goods],
        "all_world_merchandise_physically_accounted_for": True,
        "gameplay_receipt_count": len(actions),
        "full_action_receipts_held_only_during_verification": True,
        "shop_conservation_invariants_verified": True,
        "gameplay_recording_lifetime_limit_imposed": False,
        "native_Godot_gameplay_tested": False,
        "human_quality_signoff_performed": False,
    }


def stress(root: Path, *, source: str, routes: int = 4,
           intensity: int = 3) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    if type(routes) is not int or not 1 <= routes <= 8:
        raise ValueError("1..8 independent social/economy stress policies")
    if type(intensity) is not int or not 1 <= intensity <= 5:
        raise ValueError("stress workload level must be an integer 1..5")
    world, original = _load_world(root, source)
    if world.dynamics is None or world.dynamics.society is None:
        raise ValueError("social stress requires an original approved NPC economy")
    # 48..240 actions is a specialized per-scenario diagnostic budget,
    # not a restriction on game projects, authored chapters or saved turns.
    scenarios = [_probe(world, index=index, steps=48 * intensity)
                 for index in range(routes)]
    if _read(root, source, 16 * 1024 * 1024)[1] != original:
        raise ValueError("author game source changed during stress verification")
    return {
        "ok": True, "schema": SCHEMA, "action": "director-society-stress",
        "project": world.project_id, "world_sha256": world.digest,
        "source_sha256": original,
        "stress_policies": routes, "stress_workload_level": intensity,
        "all_canonical_actions_replayed_twice": True,
        "all_market_money_conserved": True,
        "scenario_reports": scenarios,
        "total_verified_actions": sum(x["actions_executed"] for x in scenarios),
        "user_project_saves_modified": False,
        "production_NPC_language_model_trained": False,
        "native_first_install_e2e_verified": False,
    }
