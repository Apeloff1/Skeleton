"""Repository-wide original-game engine execution and learning audit.

Run *real* canonical game sessions for every declared studio engine, verify
the engine's replay receipts and authored scenes, restore exact learning
snapshots, and optionally train a candidate-only Jeeves action policy. Engine
failures are reported; no run is labeled passing because an engine is merely
registered. This is not a native GPU/hardware test or a production LM update.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.advanced_gameplay_runtime import (
    ENGINES, ACTION_HELP, AdvancedRuntimeError, run_advanced_session,
    verify_advanced_session,
)
from skeleton.ai.game_builder.advanced_level_scenes import (
    make_advanced_scene, validate_advanced_scene,
)
from skeleton.ai.game_builder.system_editors import catalog
from .game_learning import GameLearningConfig, GamePolicyLearner
from .game_studio_environment import (
    StudioGameEnvironment, make_studio_source,
)

SCHEMA = "skeleton.jeeves.studio_engine_audit.v1"
MAX_ENGINES = 128
MAX_EPISODES = 8
MAX_STEPS = 16
MAX_BYTES = 4 * 1024 * 1024


def _encoded(value: object) -> bytes:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    if len(raw) > MAX_BYTES:
        raise ValueError("studio audit output exceeds finite budget")
    return raw


def _hash(value: object) -> str:
    return sha256(_encoded(value)).hexdigest()


def _registered() -> tuple[str, ...]:
    ids = tuple(sorted(ENGINES))
    catalogued = {entry["id"] for entry in catalog()}
    if len(ids) != len(set(ids)):
        raise ValueError("studio executable engine IDs are duplicated")
    if set(ids) != catalogued:
        raise ValueError(
            "studio editor registry has unmatched executable or authoring-only identities"
        )
    return ids


def inspect_engine(
    editor: str, *, seed: int, max_steps: int,
    train_episodes: int = 0, authorized: bool = False, rights_cleared: bool = False,
) -> dict[str, Any]:
    if editor not in ENGINES:
        raise ValueError("studio game engine is not executable or registered")
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise ValueError("source world seed outside advanced replay budget")
    if type(max_steps) is not int or not 1 <= max_steps <= MAX_STEPS:
        raise ValueError("studio audit step depth outside finite budget")
    if type(train_episodes) is not int or not 0 <= train_episodes <= MAX_EPISODES:
        raise ValueError("finite training episode budget required")
    if train_episodes and (authorized is not True or rights_cleared is not True):
        raise PermissionError("training audits require explicit consent and source rights")
    report: dict[str, Any] = {
        "editor": editor,
        "status": "blocked",
        "registered_actions": len(ACTION_HELP[editor]),
        "seed": seed,
        "reference_only": True,
        "native_hardware_verified": False,
        "production_neural_weights_modified": False,
        "training_enabled": bool(train_episodes),
        "source_replay_verified": False,
        "scene_replay_verified": False,
        "learning_snapshot_verified": False,
        "verified_action": None,
        "candidate_q_updates": 0,
    }
    stage = "source"
    try:
        source = make_studio_source(editor)
        source_digest = _hash(source)
        report["source_digest"] = source_digest
        config = source["settings"]
        stage = "initial game replay"
        baseline = run_advanced_session(editor, config, [], seed=seed)
        if not verify_advanced_session(baseline, config):
            raise ValueError("engine refused verified replay of its default initial state")
        report["source_replay_verified"] = True
        report["initial_game_digest"] = baseline["digest"]

        # Maze and RPG retain a separate world schema. Never pretend their
        # incompatible advanced-scene envelope is natively supported.
        if editor not in ("maze", "rpg"):
            stage = "authored scene replay"
            scene = make_advanced_scene(editor, config, seed=seed)
            verified_scene = validate_advanced_scene(scene, config)
            with_scene = run_advanced_session(
                editor, config, [], seed=seed, scene=verified_scene,
            )
            if not verify_advanced_session(with_scene, config):
                raise ValueError("authored scene did not reconstruct identical game receipt")
            report["scene_replay_verified"] = True
            report["scene_digest"] = scene["digest"]
        else:
            report["scene_skipped_reason"] = "separate_maze_rpg_source_contract"

        stage = "actual action probe"
        candidates = tuple(dict.fromkeys(
            [a for a in ("inspect", "wait", "idle", "observe", "survey", "coast",
                         "tick", "end_turn", "guard", "rest", "north", "right",
                         "accelerate", "advance", "fire", "play:0")
             if a in ACTION_HELP[editor]] + list(ACTION_HELP[editor][:32])
        ))
        accepted = None
        for action in candidates:
            try:
                played = run_advanced_session(editor, config, [action], seed=seed)
            except AdvancedRuntimeError:
                continue
            if not verify_advanced_session(played, config):
                raise ValueError("accepted gameplay command could not be verified")
            accepted = action
            report["verified_game_digest"] = played["digest"]
            report["observed_state_digest"] = played["trace"][0]["state_digest"]
            break
        if accepted is None:
            raise ValueError("engine produced no accepted registered player action")
        report["verified_action"] = accepted

        stage = "Jeeves learning protocol"
        # Audit the tested action itself as a real policy-controlled input,
        # not an unverified label or an all-commands-ready assumption.
        source = make_studio_source(editor, actions=(accepted,))
        environment = StudioGameEnvironment(source, max_steps=max_steps)
        environment.reset(seed)
        action_result = environment.step(accepted)
        if not action_result.info["evidence"]["accepted"]:
            raise ValueError("canonical game accepted a command the learning adapter rejected")
        if environment.snapshot()["source_session_digest"] == baseline["digest"]:
            raise ValueError("Jeeves learning command did not create a witnessed gameplay transition")
        saved = environment.snapshot()
        replica = StudioGameEnvironment(source, max_steps=max_steps)
        restored = replica.restore(saved)
        if replica.snapshot() != saved or dict(restored) != dict(action_result.observation):
            raise ValueError("learning snapshot did not restore by independently running the game")
        preview = environment.preview()
        if not isinstance(preview, dict) or "pixel_frame_available" not in preview:
            raise ValueError("emulator-style preview lacks explicit rendering authority")
        report["preview_digest"] = _hash(preview)
        report["learning_snapshot_verified"] = True
        report["environment_digest"] = environment.spec.environment_digest
        report["learning_transition_digest"] = action_result.transition_digest
        replica.close()
        environment.close()
        if train_episodes:
            stage = "real candidate policy optimization"
            learner = GamePolicyLearner(
                StudioGameEnvironment(source, max_steps=max_steps).spec,
                GameLearningConfig(
                    seed=seed, max_episodes=train_episodes,
                    max_updates=train_episodes * max_steps,
                ),
                policy_id="audit:" + editor + ":" + str(seed),
                source_lineage={
                    "rights_acknowledged": True,
                    "original_game_source_sha256": source_digest,
                    "execution_origin": "canonical_original_studio_replay",
                    "operator_admission": True,
                },
            )
            result = learner.train(
                lambda: StudioGameEnvironment(source, max_steps=max_steps),
                episodes=train_episodes,
            )
            if result.updates <= 0:
                raise ValueError("candidate learner did not perform any actual Q updates")
            report["candidate_q_updates"] = result.updates
            report["candidate_snapshot_digest"] = result.snapshot["snapshot_digest"]
            report["candidate_only"] = True
        report["status"] = "verified_reference_execution"
    except (ValueError, TypeError, RuntimeError, KeyError, OverflowError) as exc:
        report["failure_stage"] = stage
        report["failure_type"] = type(exc).__name__
        report["failure"] = str(exc)[:256]
    return report


def audit_studio_engines(
    engines: list[str] | tuple[str, ...] | None = None,
    *, seed: int = 17, max_steps: int = 8, train_episodes: int = 0,
    authorized: bool = False, rights_cleared: bool = False,
) -> dict[str, Any]:
    if train_episodes and (authorized is not True or rights_cleared is not True):
        raise PermissionError("actual candidate learning requires operator approval and rights clearance")
    ids = _registered()
    selection = tuple(ids if engines is None else engines)
    if not 1 <= len(selection) <= MAX_ENGINES or len(set(selection)) != len(selection):
        raise ValueError("audit selection is missing, duplicated or exceeds capacity")
    if any(engine not in ids for engine in selection):
        raise ValueError("audit selection contains an undeclared game engine")
    results = [
        inspect_engine(engine, seed=seed, max_steps=max_steps,
                       train_episodes=train_episodes,
                       authorized=authorized, rights_cleared=rights_cleared)
        for engine in selection
    ]
    verified = sum(row["status"] == "verified_reference_execution" for row in results)
    report = {
        "schema_version": SCHEMA,
        "status": "verified_reference_execution" if verified == len(selection)
                  else "blocked_unverified_engines",
        "declared_engine_count": len(ids),
        "selected_engine_count": len(selection),
        "verified_reference_engines": verified,
        "blocked_engines": len(selection) - verified,
        "actual_candidate_q_updates": sum(row["candidate_q_updates"] for row in results),
        "actual_neural_optimizer_updates": 0,
        "native_hardware_verified": False,
        "production_weights_modified": False,
        "automatic_promotion": False,
        "results": results,
    }
    return {**report, "digest": _hash(report)}


def save_report(path: Path, report: dict[str, Any]) -> str:
    if _hash({k: v for k, v in report.items() if k != "digest"}) != report["digest"]:
        raise ValueError("audit result identity changed before publication")
    target = Path(path).expanduser().absolute()
    if target.is_symlink() or not target.parent.is_dir():
        raise ValueError("audit report requires a new file in an existing directory")
    data = _encoded(report)
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return sha256(data).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engines", nargs="+", default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--train-episodes", type=int, default=0)
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--rights-cleared", action="store_true")
    args = parser.parse_args(argv)
    selection = None if args.engines is None or args.engines == ["all"] else args.engines
    report = audit_studio_engines(
        selection, seed=args.seed, max_steps=args.max_steps,
        train_episodes=args.train_episodes,
        authorized=args.authorized, rights_cleared=args.rights_cleared,
    )
    digest = save_report(args.output, report)
    print(json.dumps({
        "status": report["status"],
        "report_file_sha256": digest,
        "verified": report["verified_reference_engines"],
        "selected": report["selected_engine_count"],
        "actual_candidate_q_updates": report["actual_candidate_q_updates"],
        "production_weights_modified": False,
    }, sort_keys=True))
    return 0 if report["status"] == "verified_reference_execution" else 3


if __name__ == "__main__":
    raise SystemExit(main())
