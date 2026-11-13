"""Dragon multi-session learning lab: observed choices, not imagined preferences.

Up to ten *selected* local Director journals are independently replay-verified
before comparison. This limit applies only to an individual comparison view,
not the duration, size, or number of sessions supported by a game project.
The lesson is a provenance-bound research candidate; it never modifies weights.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from skeleton.developer.jeeves_game_director_session import _load
from skeleton.developer.jeeves_game_dragon_session import candidate as lesson

SCHEMA = "skeleton.dragon.director_comparison_lab.v1"
SESSION = re.compile(r"[a-z][a-z0-9_-]{0,55}\Z")


def _hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _names(names: str) -> tuple[str, ...]:
    if not isinstance(names, str):
        raise ValueError("--sessions requires comma-separated Director session identities")
    items = tuple(names.split(","))
    if not 2 <= len(items) <= 10 or len(set(items)) != len(items) or any(
            not SESSION.fullmatch(item) for item in items):
        raise ValueError("compare 2..10 distinct safe session names per Dragon lab pass")
    return items


def study(root: Path, *, sessions: str) -> dict[str, Any]:
    names = _names(sessions)
    samples: list[dict[str, Any]] = []
    world_id = None
    scene_ids: set[str] = set()
    all_stages: set[tuple[str, str]] = set()
    for name in names:
        _, world, state, _, _, count = _load(root, name=name)
        if world_id is not None and world_id != world.digest:
            raise ValueError("Dragon learning comparison requires identical Director world digests")
        world_id = world.digest
        scene_ids.update(s.key for s in world.scenes)
        all_stages.update((q.key, stage.key) for q in world.quests for stage in q.stages)
        datum = lesson(root, session=name)
        datum["verified_current_turn"] = state.turn
        datum["local_session_has_real_player_id"] = False
        if datum["verified_action_count"] != count:
            raise ValueError("Dragon session changed during comparative study")
        samples.append(datum)
    # Every source must still be pinned to the recorded session head.
    for sample in samples:
        _, world, state, _, head, count = _load(root, name=sample["session"])
        if (head != sample["session_head_sha256"]
                or state.digest != sample["final_director_state_sha256"]
                or count != sample["verified_action_count"]):
            raise ValueError("Dragon evidence changed during study")
    methods: dict[tuple[str, str], dict[str, tuple[str, str]]] = defaultdict(dict)
    combined_visits: Counter[str] = Counter()
    combined_uses: Counter[str] = Counter()
    routes: list[dict[str, Any]] = []
    for sample in samples:
        visited = set(sample["visited_scene_counts"])
        visited.add(world.starting_scene)
        combined_visits.update(sample["visited_scene_counts"])
        combined_uses.update(sample["mechanic_action_counts"])
        observed = {}
        for item in sample["quest_stage_results"]:
            key = (item["quest"], item["stage"])
            decision = (item["approach"], item["consequence"])
            observed[key] = decision
            methods[key][sample["session"]] = decision
        routes.append({
            "session": sample["session"],
            "session_head_sha256": sample["session_head_sha256"],
            "final_state_sha256": sample["final_director_state_sha256"],
            "actions": sample["verified_action_count"],
            "director_turns": sample["verified_current_turn"],
            "completed_campaign_logic": sample["all_quests_completed"],
            "scenes_visited": len(visited),
            "quest_stages_completed": len(observed),
            "unique_outcome_choices": len(set(observed.values())),
        })
    divergences = []
    for key in sorted(all_stages):
        observations = methods.get(key, {})
        distinct = sorted(set(observations.values()))
        if len(distinct) >= 2:
            divergences.append({
                "quest": key[0], "stage": key[1],
                "observed_outcomes": [
                    {"approach": approach, "consequence": consequence}
                    for approach, consequence in distinct
                ],
                "sessions_recorded": sorted(observations),
                "reproducibly_divergent": True,
            })
    all_visited = {world.starting_scene, *combined_visits}
    missing_stages = sorted(
        all_stages - {key for key, entries in methods.items() if entries})
    report = {
        "schema": SCHEMA,
        "project": world.project_id, "director_world_sha256": world_id,
        "sessions": list(names), "session_count": len(names),
        "routes": routes,
        "observed_stage_divergences": divergences,
        "visited_scenes": sorted(all_visited),
        "unvisited_scenes": sorted(scene_ids - all_visited),
        "stages_never_completed": [
            {"quest": quest, "stage": stage} for quest, stage in missing_stages
        ],
        "combined_scene_transition_visits": dict(sorted(combined_visits.items())),
        "combined_mechanic_uses": dict(sorted(combined_uses.items())),
        "all_samples_completed": all(x["completed_campaign_logic"] for x in routes),
        "measured_local_journal_input": True,
        "different_outcomes_verified_in_journal": bool(divergences),
        "independently_recruited_human_testers": False,
        "user_like_dislike_inferred": False,
        "actual_native_playthrough_proven": False,
        "model_weight_update_performed": False,
        "research_next": [
            "Replay unvisited scenes and quest stages with independently selected decisions",
            "Compare complete routes for systemic, not cosmetic, consequences",
            "Measure controller latency and cinematic pacing with a running engine",
            "Collect explicit consent and preference labels before supervised learning",
        ],
    }
    return report


def queue(root: Path, *, sessions: str, approved_sha256: str | None = None
          ) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    doc = study(root, sessions=sessions)
    digest = _hash(doc)
    if approved_sha256 is None:
        return {"ok": True, "action": "dragon-lab",
                "research_sha256": digest, "study": doc,
                "admitted_to_research_queue": False, "model_training_performed": False}
    if approved_sha256 != digest:
        raise ValueError("Dragon lab requires exact --approve research_sha256")
    if study(root, sessions=sessions) != doc:
        raise ValueError("Dragon gameplay journals changed while preparing research")
    base = root / ".jeeves"
    folder = base / "dragon_replay_candidates"
    for node in (base, folder):
        if node.is_symlink() or (node.exists() and not node.is_dir()):
            raise ValueError("unsafe Dragon research location")
    destination = folder / ("comparison_" + digest + ".json")
    encoded = (json.dumps(doc, sort_keys=True, indent=2,
                          ensure_ascii=True, allow_nan=False) + "\n").encode()
    if len(encoded) > 4 * 1024 * 1024:
        raise ValueError("comparative Dragon research record exceeds local capacity")
    _create_only(destination, encoded)
    return {"ok": True, "action": "dragon-lab",
            "research_sha256": digest, "path": str(destination),
            "admitted_to_research_queue": True, "model_training_performed": False}
