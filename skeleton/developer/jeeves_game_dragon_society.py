"""Dragon society research from independently replayed original-world actions.

Only source-reviewed, cryptographically chained game actions can be studied.
This is deterministic instrumentation, not hidden sentiment inference or an
LLM checkpoint weight update. Long sessions are counted completely; only
human-readable event highlights are bounded per research receipt.
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
from skeleton.ai.game_builder.quest_society import phase, residents_here
from skeleton.developer.jeeves_game_director_session import _load, _read_doc

SCHEMA = "skeleton.dragon.original_society_study.v1"


def _hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def study(root: Path, *, session: str) -> dict[str, Any]:
    folder, world, final, manifest, head, count = _load(root, name=session)
    if (world.dynamics is None or world.dynamics.society is None
            or final.world_state.society is None):
        raise ValueError("Dragon society analysis requires a real approved NPC society")
    rules = world.dynamics.society
    start = director_initial(world)
    state = start
    contacts: Counter[str] = Counter()
    chosen_topics: Counter[str] = Counter()
    buys: Counter[str] = Counter()
    sells: Counter[str] = Counter()
    interactions_by_period: Counter[str] = Counter()
    interactions_by_location: Counter[str] = Counter()
    NPC_appearances: Counter[str] = Counter()
    wallet_gains = wallet_spending = 0
    social_time = trade_time = rest_time = 0
    unlocked_flags: dict[str, int] = {}
    first_meet: dict[str, int] = {}
    shop_out_of_stock = Counter()
    trust_changed = Counter()
    event_count = 0
    examples: list[dict[str, Any]] = []
    for sequence in range(1, count + 1):
        item = _read_doc(folder / f"{sequence:08d}.json")
        action = DirectorAction(**item["action"])
        if action not in available_director_actions(world, state):
            raise ValueError("Dragon study found an unauthorised historical NPC action")
        before = state
        if item["before_sha256"] != before.digest:
            raise ValueError("NPC evidence prior state does not match real game")
        state = director_step(world, state, action)
        if item["after_sha256"] != state.digest:
            raise ValueError("NPC evidence after state differs from replay")
        old = before.world_state.society
        next_society = state.world_state.society
        if old is None or next_society is None:
            raise ValueError("NPC economy disappeared during canonical action")
        calendar = phase(rules, before.turn)
        interactions_by_period[calendar["phase"]] += 1
        interactions_by_location[before.scene] += 1
        for person in residents_here(rules, before.scene, before.turn):
            NPC_appearances[person.key] += 1
            first_meet.setdefault(person.key, sequence)
        delta_money = next_society.balance - old.balance
        wallet_gains += max(0, delta_money)
        wallet_spending += max(0, -delta_money)
        if action.kind == "speak":
            contacts[action.key] += 1
            social_time += state.turn - before.turn
        elif action.kind == "discuss":
            npc, topic = next(
                (n, choice) for n in rules.residents for choice in n.dialogue
                if n.key + "_" + choice.key == action.key
            )
            contacts[npc.key] += 1
            chosen_topics[npc.key + ":" + topic.key] += 1
            social_time += state.turn - before.turn
        elif action.kind == "buy":
            buys[action.key] += 1
            trade_time += state.turn - before.turn
        elif action.kind == "sell":
            sells[action.key] += 1
            trade_time += state.turn - before.turn
        elif action.kind == "rest":
            rest_time += state.turn - before.turn
        previous_rel = dict(old.relationships)
        for npc, value in next_society.relationships:
            if previous_rel[npc] != value:
                trust_changed[npc] += 1
        previous_flags = set(before.world_state.world_flags)
        new_flags = sorted(set(state.world_state.world_flags) - previous_flags)
        if not previous_flags.issubset(state.world_state.world_flags):
            raise ValueError("NPC study saw an erased permanent world event")
        for flag in new_flags:
            unlocked_flags[flag] = sequence
        # The social economy is not assumed to be good just because it is
        # deterministic. Preserve small objective evidence samples.
        if (action.kind in {"speak", "discuss", "buy", "sell", "rest"} or new_flags):
            event_count += 1
            if len(examples) < 100:
                examples.append({
                    "sequence": sequence, "action": action.payload(),
                    "time_phase": calendar["phase"],
                    "game_scene": before.scene,
                    "wallet_before": old.balance,
                    "wallet_after": next_society.balance,
                    "new_world_flags": new_flags,
                    "state_sha256": state.digest,
                })
        # Track shops whose stock was depleted by the actual replay, not
        # fictional unsatisfied customers.
        previous_stock = {(s, g): n for s, g, n in old.shop_stock}
        for shop, good, stock in next_society.shop_stock:
            if stock == 0 and previous_stock[(shop, good)] > 0:
                shop_out_of_stock[shop + ":" + good] += 1
    if state != final:
        raise ValueError("Dragon study does not recover independently verified last save")
    # The source, journal and approval identity must remain unchanged.
    _, latest_world, latest_state, latest_manifest, latest_head, latest_count = _load(
        root, name=session
    )
    if (latest_world.digest != world.digest or latest_state != final
            or latest_manifest["source_sha256"] != manifest["source_sha256"]
            or latest_head != head or latest_count != count):
        raise ValueError("NPC research source or replay advanced during study")
    base = start.world_state.society
    return {
        "schema": SCHEMA, "session": session, "project": world.project_id,
        "world_sha256": world.digest,
        "source_sha256": manifest["source_sha256"],
        "session_head_sha256": head, "action_count": count,
        "initial_state_sha256": start.digest,
        "ending_state_sha256": state.digest,
        "initial_wallet": base.balance,
        "ending_wallet": state.world_state.society.balance,
        "money_spent_on_real_actions": wallet_spending,
        "money_received_from_real_actions": wallet_gains,
        "talk_count_by_resident": dict(sorted(contacts.items())),
        "dialogue_topic_selection_counts": dict(sorted(chosen_topics.items())),
        "authored_replies_were_verified_not_invented": True,
        "buy_count_by_shop_good": dict(sorted(buys.items())),
        "sell_count_by_shop_good": dict(sorted(sells.items())),
        "recorded_game_actions_by_period": dict(sorted(interactions_by_period.items())),
        "recorded_game_actions_by_scene": dict(sorted(interactions_by_location.items())),
        "npc_present_during_recorded_actions": dict(sorted(NPC_appearances.items())),
        "first_observed_npc_presence_sequence": dict(sorted(first_meet.items())),
        "trust_changed_by_resident": dict(sorted(trust_changed.items())),
        "initial_relationships": dict(base.relationships),
        "final_relationships": dict(state.world_state.society.relationships),
        "actual_persisted_dialogue_choice_history": [
            list(x) for x in state.world_state.society.dialogue_history],
        "interaction_turns": social_time,
        "trade_turns": trade_time, "rest_turns": rest_time,
        "world_flag_unlock_sequence": dict(sorted(unlocked_flags.items())),
        "shop_depletion_events": dict(sorted(shop_out_of_stock.items())),
        "society_evidence_sample": examples,
        "society_evidence_event_count": event_count,
        "society_evidence_sample_complete": event_count <= 100,
        "real_shop_stock": [list(x) for x in state.world_state.society.shop_stock],
        "real_purchased_inventory": [list(x) for x in state.world_state.society.owned],
        "gameplay_evidence_replayed": True,
        "player_satisfaction_inferred": False,
        "NPC_dialogue_emotional_quality_certified": False,
        "real_model_training_performed": False,
        "native_Godot_NPC_behavior_verified": False,
    }


def compare(root: Path, *, first: str, second: str) -> dict[str, Any]:
    a, b = study(root, session=first), study(root, session=second)
    if (a["world_sha256"] != b["world_sha256"]
            or a["source_sha256"] != b["source_sha256"]):
        raise ValueError("society comparison needs same approved original world")
    differences = [{
        "npc": key,
        "first": a["final_relationships"][key],
        "second": b["final_relationships"][key],
        "trust_difference": b["final_relationships"][key] - a["final_relationships"][key],
    } for key in sorted(a["final_relationships"])
        if a["final_relationships"][key] != b["final_relationships"][key]]
    return {
        "ok": True, "action": "dragon-society-contrast",
        "schema": SCHEMA, "first": first, "second": second,
        "world_sha256": a["world_sha256"],
        "source_sha256": a["source_sha256"],
        "first_head_sha256": a["session_head_sha256"],
        "second_head_sha256": b["session_head_sha256"],
        "trust_differences": differences,
        "wallet_difference": b["ending_wallet"] - a["ending_wallet"],
        "transaction_counts": {
            first: sum(a["buy_count_by_shop_good"].values())
                   + sum(a["sell_count_by_shop_good"].values()),
            second: sum(b["buy_count_by_shop_good"].values())
                    + sum(b["sell_count_by_shop_good"].values()),
        },
        "model_weights_changed": False,
        "comparison_is_objective_replayed_gameplay": True,
    }


def queue(root: Path, *, session: str,
          approved_sha256: str | None = None) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    receipt = study(root, session=session)
    digest = _hash(receipt)
    if approved_sha256 is None:
        return {
            "ok": True, "action": "dragon-society-study",
            "study": receipt, "study_sha256": digest,
            "admitted_for_training_review": False, "production_weights_updated": False,
        }
    if approved_sha256 != digest:
        raise ValueError("Dragon society admission needs exact approved SHA256 receipt")
    if study(root, session=session) != receipt:
        raise ValueError("NPC journal advanced after reviewing research evidence")
    base = root / ".jeeves"
    folder = base / "dragon_replay_candidates"
    for directory in (base, folder):
        if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
            raise ValueError("unsafe Dragon replay evidence folder")
    path = folder / ("society_" + digest + ".json")
    raw = (json.dumps(receipt, ensure_ascii=True, sort_keys=True,
                      indent=2, allow_nan=False) + "\n").encode()
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("society evidence exceeds bounded manual review packet")
    _create_only(path, raw)
    return {
        "ok": True, "action": "dragon-society-study",
        "study_sha256": digest,
        "path": str(path), "admitted_for_training_review": True,
        "production_weights_updated": False,
    }
