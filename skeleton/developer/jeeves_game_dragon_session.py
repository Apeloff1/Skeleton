"""Dragon research queue backed by actual human-selected Director CLI actions.

This is a verifiable *input journal* and training-dataset candidate, not a
claim that the user played the rendered game or endorsed any preference.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from skeleton.developer.jeeves_game_director_session import _load, _read_doc
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.dragon.interactive_director_learning_candidate.v1"


def _hash(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def candidate(root: Path, *, session: str) -> dict[str, Any]:
    folder, world, state, manifest, tip, count = _load(root, name=session)
    mechanics = Counter()
    regions = Counter()
    paths = []
    previous_scene = world.starting_scene
    for i in range(1, count + 1):
        receipt = _read_doc(folder / f"{i:08d}.json")
        action = receipt["action"]
        if action["kind"] == "travel":
            regions[action["key"]] += 1
            paths.append([previous_scene, action["key"]])
            previous_scene = action["key"]
        elif action["kind"] == "use":
            scene = next(scene for scene in world.scenes if scene.key == action["scene"])
            affordance = next(a for a in scene.affordances if a.key == action["key"])
            mechanics[affordance.kind] += 1
        else:
            mechanics["wait"] += 1
    output = {
        "schema": SCHEMA,
        "project": world.project_id, "session": session,
        "director_world_sha256": world.digest,
        "source": manifest["source"], "source_sha256": manifest["source_sha256"],
        "session_head_sha256": tip, "verified_action_count": count,
        "final_director_state_sha256": state.digest,
        "quest_stage_results": [r.payload() for r in state.results],
        "navigation_edges": paths,
        "visited_scene_counts": dict(sorted(regions.items())),
        "mechanic_action_counts": dict(sorted(mechanics.items())),
        "all_quests_completed": len(state.complete) == len(world.quests),
        "verified_action_origin": "local-CLI-choice-inputs",
        "actual_native_frames_observed": False,
        "controller_inputs_verified_on_hardware": False,
        "player_preferences_measured": False,
        "model_training_started": False,
        "research_questions": [
            "Compare this action sequence to actual rendered gameplay from the same authored scene graph",
            "Look for navigation congestion or excessive travel between quest stages",
            "Request independent player review of mechanic responsiveness and narrative consequence",
            "Gather licensed, consented gameplay captures before teaching Dragon visual behaviors",
        ],
    }
    return output


def enqueue(root: Path, *, session: str, approved_digest: str | None = None
            ) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    payload = candidate(root, session=session)
    digest = _hash(payload)
    if approved_digest is None:
        return {"ok": True, "action": "dragon-session-lesson",
                "candidate_sha256": digest, "candidate": payload,
                "admitted_to_research_queue": False, "trained_model_weights": False}
    if approved_digest != digest:
        raise ValueError("--approve must match the full exact reviewed session candidate")
    base = root / ".jeeves"
    folder = base / "dragon_replay_candidates"
    if base.is_symlink() or (base.exists() and not base.is_dir()) or (
            folder.is_symlink() or (folder.exists() and not folder.is_dir())):
        raise ValueError("unsafe Dragon research queue path")
    # Rebuild from entire live action journal to prevent stale-context enqueue.
    if candidate(root, session=session) != payload:
        raise ValueError("Director session changed while Dragon research was being admitted")
    destination = folder / ("interactive_" + digest + ".json")
    _create_only(destination, (json.dumps(payload, sort_keys=True, indent=2,
                                          allow_nan=False) + "\n").encode())
    return {"ok": True, "action": "dragon-session-lesson",
            "candidate_sha256": digest, "path": str(destination),
            "admitted_to_research_queue": True, "trained_model_weights": False}
