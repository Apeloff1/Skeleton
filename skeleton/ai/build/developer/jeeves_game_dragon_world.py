"""Dragon living-world research built from actual canonical Director journals.

Unlike fabricated preference training, this reconstructs faction standing,
unlocking history, consumed fares, transit exposure and quest consequences.
A reviewed SHA receipt can enter the queue, but nothing is promoted into
the Jeeves transformer, paid services, or another user's model.
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
from skeleton.developer.jeeves_game_director_session import (
    _load, _read_doc,
)

SCHEMA = "skeleton.dragon.director_world_dynamics_study.v1"
MAX_EVIDENCE = 4 * 1024 * 1024


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _standing_delta(before: Any, after: Any) -> list[dict[str, Any]]:
    left, right = dict(before.standings), dict(after.standings)
    return [
        {"faction": key, "before": left[key], "after": right[key],
         "delta": right[key] - left[key]}
        for key in sorted(left)
        if left[key] != right[key]
    ]


def study(root: Path, *, session: str) -> dict[str, Any]:
    folder, world, end_state, manifest, head, action_count = _load(root, name=session)
    if world.dynamics is None or end_state.world_state is None:
        raise ValueError("Dragon world research requires an actual authored dynamic world")
    state = director_initial(world)
    modes: Counter[str] = Counter()
    journeys: Counter[str] = Counter()
    choices: Counter[str] = Counter()
    unlocked: list[dict[str, Any]] = []
    standing_change: list[dict[str, Any]] = []
    consumed = Counter()
    earned = Counter()
    completed_quests = Counter()
    stage_consequences = Counter()
    blocked_before = Counter()
    blocked_after = Counter()
    turns = Counter()
    route_details = {p.key: p for p in world.dynamics.passages}

    def blocked(current: Any) -> set[tuple[str, str, str]]:
        from skeleton.ai.game_builder.quest_world_dynamics import permits
        return {
            ("walk", gate.source, gate.destination) for gate in world.dynamics.gates
            if gate.source == current.scene and not permits(gate.requirements, current)
        } | {
            ("transit", passage.key, passage.destination if current.scene == passage.source
             else passage.source)
            for passage in world.dynamics.passages
            if ((passage.source == current.scene or
                 passage.bidirectional and passage.destination == current.scene)
                and not permits(passage.requirements, current))
        }

    for index in range(1, action_count + 1):
        item = _read_doc(folder / f"{index:08d}.json")
        action = DirectorAction(**item["action"])
        if action not in available_director_actions(world, state):
            raise ValueError("Dragon cannot learn from unavailable historical action")
        old = state
        old_blocked = blocked(old)
        state = director_step(world, state, action)
        if item["before_sha256"] != old.digest or item["after_sha256"] != state.digest:
            raise ValueError("Dragon world evidence differs from canonical action receipt")
        new_blocked = blocked(state)
        if action.kind == "travel":
            modes["foot"] += 1
            journeys[old.scene + "→" + state.scene] += 1
        elif action.kind == "transit":
            route = route_details.get(action.key)
            if route is None:
                raise ValueError("unrecognized world transit in persisted game")
            modes[route.mode] += 1
            journeys[old.scene + "→" + state.scene] += 1
            choices["transit:" + action.key] += 1
        elif action.kind == "use":
            choices["use:" + action.key] += 1
        else:
            choices["wait"] += 1
        turns[action.kind] += state.turn - old.turn
        for entry in _standing_delta(old.world_state, state.world_state):
            standing_change.append({"sequence": index, **entry,
                                    "action": action.kind + ":" + action.key})
        if len(standing_change) > 100:
            # Preserve a bounded evidence highlight set, not an unbounded
            # memory footprint. Aggregate last-standing values are exact.
            standing_change.pop(0)
        new_flags = sorted(
            set(state.world_state.world_flags) - set(old.world_state.world_flags))
        for flag in new_flags:
            unlocked.append({"sequence": index, "world_flag": flag,
                             "caused_by_action": action.kind + ":" + action.key,
                             "state_sha256": state.digest})
        for asset in set(old.acquired) - set(state.acquired):
            consumed[asset] += 1
        for asset in set(state.acquired) - set(old.acquired):
            earned[asset] += 1
        for quest in set(state.complete) - set(old.complete):
            completed_quests[quest] += 1
        for result in state.results[len(old.results):]:
            stage_consequences[result.consequence] += 1
        for kind, source, dest in old_blocked:
            blocked_before[kind + ":" + source + ":" + dest] += 1
        for kind, source, dest in new_blocked:
            blocked_after[kind + ":" + source + ":" + dest] += 1
    if state != end_state:
        raise ValueError("Dragon world study final state is not reproducible")
    # Repeat the global manifest and terminal head verification before any
    # preview/admission can be identified as current.
    _, live_world, live_state, live_manifest, live_head, live_actions = _load(
        root, name=session,
    )
    if (live_world.digest != world.digest or live_state != end_state
            or live_head != head or live_actions != action_count
            or live_manifest["source_sha256"] != manifest["source_sha256"]):
        raise ValueError("Dragon world-study evidence changed during review")
    details = {
        "schema": SCHEMA, "project": world.project_id,
        "world_sha256": world.digest,
        "source_sha256": manifest["source_sha256"],
        "session": session, "session_head_sha256": head,
        "verified_action_count": action_count, "canonical_final_sha256": state.digest,
        "mode_use_counts": dict(sorted(modes.items())),
        "journey_counts": dict(sorted(journeys.items())),
        "action_counts": dict(sorted(choices.items())),
        "turns_by_action_kind": dict(sorted(turns.items())),
        "reputation_change_highlights": standing_change,
        "actual_faction_standings": dict(state.world_state.standings),
        "world_flags_unlocked": unlocked,
        "consumed_inventory_counts": dict(sorted(consumed.items())),
        "gained_inventory_counts": dict(sorted(earned.items())),
        "completed_quest_counts": dict(sorted(completed_quests.items())),
        "outcome_counts": dict(sorted(stage_consequences.items())),
        "gate_observations_before_actions": dict(sorted(blocked_before.items())),
        "gate_observations_after_actions": dict(sorted(blocked_after.items())),
        "actual_passage_use_counts": dict(state.world_state.passage_uses),
        "transport_congestion_inferred_from_user_taste": False,
        "user_sentiment_or_happiness_measured": False,
        "independent_human_comparison_verified": False,
        "production_model_weights_trained": False,
        "native_performance_instrumented": False,
        "research_questions": [
            "Review whether gated alternatives preserve complete story agency",
            "Check whether unique ticket sinks produce unintended one-way softlocks",
            "Compare separate consented gameplay runs for route variance",
            "Test original Godot transport animations and audio against author direction",
            "Evaluate faction morality effects and outcome consistency with reviewers",
        ],
    }
    return details


def compare(root: Path, *, first: str, second: str) -> dict[str, Any]:
    a, b = study(root, session=first), study(root, session=second)
    if a["world_sha256"] != b["world_sha256"] or a["source_sha256"] != b["source_sha256"]:
        raise ValueError("Dragon faction comparison requires exact same approved world")
    standing_a = a["actual_faction_standings"]
    standing_b = b["actual_faction_standings"]
    standing_diff = [
        {"faction": faction,
         "first": standing_a[faction], "second": standing_b[faction],
         "difference": standing_b[faction] - standing_a[faction]}
        for faction in sorted(standing_a) if standing_a[faction] != standing_b[faction]
    ]
    return {
        "ok": True, "action": "dragon-world-contrast",
        "schema": SCHEMA, "first": first, "second": second,
        "world_sha256": a["world_sha256"],
        "first_head_sha256": a["session_head_sha256"],
        "second_head_sha256": b["session_head_sha256"],
        "standing_differences": standing_diff,
        "different_world_flags": {
            "first_only": sorted({x["world_flag"] for x in a["world_flags_unlocked"]}
                                 - {x["world_flag"] for x in b["world_flags_unlocked"]}),
            "second_only": sorted({x["world_flag"] for x in b["world_flags_unlocked"]}
                                  - {x["world_flag"] for x in a["world_flags_unlocked"]}),
        },
        "transport_usage_comparison": {
            "first": a["mode_use_counts"], "second": b["mode_use_counts"],
        },
        "human_pref_or_reward_inferred": False,
        "model_weights_updated": False,
        "read_only_verified_canonical_replay": True,
    }


def queue(root: Path, *, session: str,
          approved_sha256: str | None = None) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    content = study(root, session=session)
    digest = _hash(content)
    if approved_sha256 is None:
        return {
            "ok": True, "action": "dragon-world-study",
            "study": content, "study_sha256": digest,
            "admitted_to_research_queue": False,
            "production_model_weights_updated": False,
        }
    if approved_sha256 != digest:
        raise ValueError("Dragon world study requires exact --approve identity")
    if study(root, session=session) != content:
        raise ValueError("world or session changed while admitting a Dragon research receipt")
    base = root / ".jeeves"
    folder = base / "dragon_replay_candidates"
    for node in (base, folder):
        if node.is_symlink() or (node.exists() and not node.is_dir()):
            raise ValueError("unsafe Dragon research directory")
    payload = (json.dumps(content, sort_keys=True, indent=2,
                          ensure_ascii=True, allow_nan=False) + "\n").encode()
    if len(payload) > MAX_EVIDENCE:
        raise ValueError("Dragon replay evidence exceeds bounded research packet capacity")
    destination = folder / ("world_" + digest + ".json")
    _create_only(destination, payload)
    return {
        "ok": True, "action": "dragon-world-study",
        "study_sha256": digest, "path": str(destination),
        "admitted_to_research_queue": True,
        "model_weights_updated": False,
    }
