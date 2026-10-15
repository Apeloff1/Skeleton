"""Train a REAL local Jeeves game-action policy on canonical original engines.

This command executes the identical replay-backed environment contract as
Jeeves's emulator policy training, performs actual bounded Q updates and saves
a candidate policy with episode evidence. It does NOT modify or impersonate
production Jeeves neural checkpoints, and never auto-promotes learned policies.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .game_learning import GameLearningConfig, GamePolicyLearner
from .game_learning_parallel import GameEnvironmentRequest
from .game_studio_environment import make_studio_source, studio_request_tree


def train_studio_policy(
    *, editor: str, output: Path, authorized: bool, rights_cleared: bool,
    episodes: int = 8, max_steps: int = 32, seed: int = 0,
    settings: dict | None = None, actions: tuple[str, ...] | None = None,
) -> dict:
    if authorized is not True or rights_cleared is not True:
        raise PermissionError("original game training requires explicit operator and source-rights admission")
    if type(episodes) is not int or not 1 <= episodes <= 128:
        raise ValueError("bounded training episodes must be in [1,128]")
    if type(seed) is not int or not 0 <= seed <= 2**63-1:
        raise ValueError("bounded policy seed required")
    source = make_studio_source(editor, settings, actions=actions)
    request = GameEnvironmentRequest(
        "studio:" + editor, kind="studio", tree=studio_request_tree(source),
        max_steps=max_steps,
    )
    environment = request.build()
    spec = environment.spec
    environment.close()
    learner = GamePolicyLearner(
        spec, GameLearningConfig(seed=seed, max_episodes=episodes,
                                 max_updates=episodes * max_steps),
        policy_id="studio:" + editor + ":" + str(seed),
        source_lineage={
            "rights_acknowledged": True,
            "original_game_source_sha256": request.digest,
            "execution_origin": "canonical_studio_game_environment",
            "operator_admission": True,
        },
    )
    result = learner.train(request.build, episodes=episodes)
    if result.updates <= 0:
        raise RuntimeError("training returned zero real policy updates")
    record = {
        "schema_version": "skeleton.game_builder.policy_candidate.v1",
        "editor": editor,
        "status": "candidate_trained_not_promoted",
        "environment_request_digest": request.digest,
        "environment": spec.as_dict(),
        "policy_snapshot": result.snapshot,
        "actual_q_updates": result.updates,
        "episodes": [entry for entry in result.episode_summaries],
        "gameplay_evidence": [trace["trace_digest"] for trace in result.traces],
        "production_neural_weights_modified": False,
        "automatic_promotion": False,
    }
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False, allow_nan=False).encode()
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("candidate policy exceeds fixed admission capacity")
    destination = Path(output).expanduser().absolute()
    if not destination.parent.is_dir() or destination.is_symlink():
        raise ValueError("candidate parent must exist and target must not be a symlink")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return {
        "candidate": str(destination), "editor": editor,
        "episodes": episodes, "q_updates": result.updates,
        "policy_snapshot_digest": result.snapshot["snapshot_digest"],
        "promotion": "not_authorized",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=8)
    parser.add_argument("--max-steps", type=int, default=32)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--settings-json")
    parser.add_argument("--actions", nargs="+")
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--rights-cleared", action="store_true")
    args = parser.parse_args(argv)
    settings = json.loads(args.settings_json) if args.settings_json else None
    output = train_studio_policy(
        editor=args.engine, output=args.output,
        episodes=args.episodes, max_steps=args.max_steps,
        seed=args.seed, settings=settings,
        actions=tuple(args.actions) if args.actions else None,
        authorized=args.authorized, rights_cleared=args.rights_cleared,
    )
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
