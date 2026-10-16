"""Dragon's evidence-grounded navigation/maze learning digest.

Measures how actual Director session traversal differs from the shortest
authored route between successive world interactions. A detour may be
intentional exploration; do not label it a defect or infer player enjoyment.
"""
from __future__ import annotations

from collections import Counter, deque
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, director_initial, director_step,
)
from skeleton.developer.jeeves_game_director_session import _hash, _load, _read_doc
from skeleton.developer.jeeves_game_director_labyrinth import _graph
from skeleton.developer.jeeves_game_director_causality import audit

SCHEMA = "skeleton.dragon.director_navigation_study.v1"


def _shortest(graph: dict[str, tuple[str, ...]], origin: str, target: str) -> int:
    if origin == target:
        return 0
    queue = deque([(origin, 0)])
    seen = {origin}
    while queue:
        scene, depth = queue.popleft()
        for neighbor in graph[scene]:
            if neighbor == target:
                return depth + 1
            if neighbor not in seen:
                seen.add(neighbor)
                queue.append((neighbor, depth + 1))
    raise ValueError("recorded game journey contains an unreachable authored destination")


def study(root: Path, *, session: str) -> dict[str, Any]:
    folder, world, final, source, head, count = _load(root, name=session)
    graph = _graph(world)
    state = director_initial(world)
    start = state.scene
    moved = 0
    visited: Counter[str] = Counter({start: 1})
    episodes = []
    full_walk: list[str] = [start]
    total_hops = total_shortest = 0
    use_interactions = 0
    waits = 0

    def close(reason: str, index: int) -> None:
        nonlocal start, moved, total_hops, total_shortest, full_walk
        if not moved:
            start = state.scene
            return
        shortest = _shortest(graph, start, state.scene)
        surplus = moved - shortest
        if surplus < 0:
            raise ValueError("authored shortest path exceeds actual valid replayed journey")
        total_hops += moved
        total_shortest += shortest
        episodes.append({
            "end_sequence": index, "boundary": reason,
            "origin": start, "destination": state.scene,
            "actual_hops": moved, "shortest_hops": shortest,
            "extra_hops_vs_shortest": surplus,
            "walk": full_walk[-min(len(full_walk), 32):],
            "not_evidence_of_bad_player_behavior": True,
        })
        start, moved, full_walk = state.scene, 0, [state.scene]

    for index in range(1, count + 1):
        item = _read_doc(folder / f"{index:08d}.json")
        step = DirectorAction(**item["action"])
        if item["before_sha256"] != state.digest:
            raise ValueError("Dragon maze evidence diverges from canonical replay")
        state = director_step(world, state, step)
        if item["after_sha256"] != state.digest:
            raise ValueError("Dragon maze evidence action hash differs")
        if step.kind == "travel":
            moved += 1
            visited[state.scene] += 1
            full_walk.append(state.scene)
        elif step.kind == "use":
            use_interactions += 1
            close("interaction", index)
        else:
            waits += 1
            close("wait", index)
    close("session_end", count)
    if final != state:
        raise ValueError("Dragon route digest does not match independent journal replay")
    causal = audit(root, session=session, page=1, page_size=1)
    if (causal["summary"]["journal_head_sha256"] != head
            or causal["summary"]["end_state_sha256"] != state.digest):
        raise ValueError("Dragon labyrinth evidence changed during independent causality audit")
    material = sorted(episodes, key=lambda x: (
        -x["extra_hops_vs_shortest"], -x["actual_hops"], x["end_sequence"]
    ))[:20]
    report = {
        "schema": SCHEMA, "project": world.project_id, "session": session,
        "world_sha256": world.digest, "source_sha256": source["source_sha256"],
        "journal_head_sha256": head, "canonical_state_sha256": state.digest,
        "causal_summary_sha256": causal["summary_sha256"],
        "actions_verified": count, "travel_hops": total_hops,
        "reference_shortest_hops": total_shortest,
        "surplus_travel_hops_vs_reference": total_hops - total_shortest,
        "travel_episode_count": len(episodes), "interaction_actions": use_interactions,
        "wait_actions": waits,
        "scene_entrance_counts": dict(sorted(visited.items())),
        "largest_route_deviations": material,
        "unique_scenes_visited": len(visited),
        "player_exploration_preference_inferred": False,
        "navigation_journey_was_actual_director_actions": True,
        "native_pathfinding_hardware_playtest_verified": False,
        "weights_or_model_promoted": False,
        "interpretation": ("Surplus travel measures deviations from shortest traversals "
                           "between real interaction boundaries; it does not "
                           "distinguish mistakes from meaningful scenic choices."),
    }
    return report


def queue(root: Path, *, session: str, approved_digest: str | None = None
          ) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    record = study(root, session=session)
    identity = _hash(record)
    if approved_digest is None:
        return {
            "ok": True, "action": "dragon-navigation-study", "study": record,
            "study_sha256": identity, "admitted_to_research": False,
            "model_weights_updated": False,
        }
    if approved_digest != identity:
        raise ValueError("--approve must match exact source-bound Dragon navigation study")
    # Re-evaluate entire action history and canonical consequences immediately
    # before publication; never borrow evidence from another session.
    if study(root, session=session) != record:
        raise ValueError("gameplay changed during Dragon research admission")
    base = root / ".jeeves"
    folder = base / "dragon_replay_candidates"
    for node in (base, folder):
        if node.is_symlink() or (node.exists() and not node.is_dir()):
            raise ValueError("unsafe Dragon research queue directory")
    content = ( __import__("json").dumps(
        record, sort_keys=True, ensure_ascii=True, indent=2,
        allow_nan=False) + "\n").encode()
    if len(content) > 2 * 1024 * 1024:
        raise ValueError("Dragon labyrinth research receipt exceeds batch size")
    location = folder / ("navigation_" + identity + ".json")
    _create_only(location, content)
    return {
        "ok": True, "action": "dragon-navigation-study", "path": str(location),
        "study_sha256": identity, "admitted_to_research": True,
        "model_weights_updated": False,
    }
