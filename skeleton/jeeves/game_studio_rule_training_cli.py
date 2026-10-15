"""Train an actual candidate Jeeves game-action policy across AI-proposed rule variants.

The proposal file is untrusted data. It never grants execution rights; the
operator must explicitly admit original-game rights and candidate training.
Baseline and modified source rules are independently revalidated. This uses
the same measured Q-learning loop as the emulator system and evaluates on
disjoint, seed-stratified scenarios. It never changes production neural weights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from .game_learning import GameLearningConfig, GamePolicyLearner
from .game_learning_parallel import GameEnvironmentRequest
from .game_studio_environment import make_studio_source, parse_studio_source
from .game_studio_rule_curriculum import (
    PLAN_SCHEMA, PROPOSAL_SCHEMA, RuleCurriculumEnvironment,
    RuleCurriculumError, make_rule_curriculum,
)

MAX_BATCH_BYTES = 65536


def _read_json(path: Path, *, limit: int):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 1 <= path.stat().st_size <= limit:
        raise RuleCurriculumError("source/proposal input must be bounded regular JSON")
    raw = path.read_bytes()
    if len(raw) > limit:
        raise RuleCurriculumError("AI proposal source changed while opening")
    def duplicates(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise RuleCurriculumError("duplicate JSON key in AI rule candidate")
            result[key] = value
        return result
    try:
        return json.loads(
            raw, object_pairs_hook=duplicates,
            parse_constant=lambda _: (_ for _ in ()).throw(
                RuleCurriculumError("nonfinite AI rule value")),
        )
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise RuleCurriculumError("rule file contains invalid JSON") from exc


def _write_candidate(output: Path, record: dict) -> str:
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("utf-8")
    if len(raw) > 8 * 1024 * 1024:
        raise RuleCurriculumError("measured candidate exceeds policy storage budget")
    target = Path(output).expanduser().absolute()
    if target.is_symlink() or not target.parent.is_dir():
        raise RuleCurriculumError("candidate output needs existing private parent directory")
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as writer:
            writer.write(raw)
            writer.flush()
            os.fsync(writer.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return hashlib.sha256(raw).hexdigest()


def train_rule_curriculum(
    *, base_source: dict, proposals: list[dict], output: Path,
    authorized: bool, rights_cleared: bool, seed: int = 0,
    episodes_per_scenario: int = 4, max_steps: int = 24,
    neural_corpus_output: Path | None = None,
) -> dict:
    """Train *one* scenario-conditioned Q policy and independently evaluate it."""
    if authorized is not True or rights_cleared is not True:
        raise PermissionError(
            "original game AI-rule training requires explicit operator and source-rights consent"
        )
    if (type(seed) is not int or not 0 <= seed <= 2**63 - 1 or
            type(episodes_per_scenario) is not int or
            not 1 <= episodes_per_scenario <= 16):
        raise RuleCurriculumError("seed or per-circumstance episode budget invalid")
    plan = make_rule_curriculum(base_source, proposals, max_steps=max_steps)
    circumstances = len(plan["scenarios"])
    count = circumstances * episodes_per_scenario
    if count > 128:
        raise RuleCurriculumError("training policy episode capacity exceeded")
    request = GameEnvironmentRequest(
        "studio-rules:" + plan["base_source"]["editor"], kind="studio_rules",
        tree={"game/studio/rule_curriculum.json": json.dumps(
            plan, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        )},
        max_steps=max_steps,
    )
    env = request.build()
    try:
        spec = env.spec
    finally:
        env.close()
    learner = GamePolicyLearner(
        spec, GameLearningConfig(
            seed=seed, max_episodes=count, max_updates=count * max_steps,
        ),
        policy_id="studio-rules:" + base_source["editor"] + ":" + str(seed),
        source_lineage={
            "origin": "verified_ai_proposed_rule_curriculum",
            "operator_rights_acknowledged": True,
            "original_game_source_sha256": hashlib.sha256(json.dumps(
                parse_studio_source(base_source), sort_keys=True,
                separators=(",", ":"), ensure_ascii=True,
            ).encode("utf-8")).hexdigest(),
            "rule_curriculum_digest": plan["digest"],
            "actual_game_rules_changed_by_scenario": True,
        },
    )
    previous = learner.snapshot()
    # A round-robin modulo scheme proves each training scenario is visited.
    # Evaluation seeds are disjoint from *all* training seeds, no matter which
    # candidate the agent selected during the earlier rollout.
    train_seeds = [
        seed + index * circumstances + scenario
        for index in range(episodes_per_scenario)
        for scenario in range(circumstances)
    ]
    if train_seeds[-1] > 2**63 - 1:
        raise RuleCurriculumError("scenario training seeds overflow the transport budget")
    eval_base = seed + 1_000_000
    if eval_base + circumstances > 2**63 - 1:
        raise RuleCurriculumError("disjoint evaluation seed budget overflow")
    heldout = [eval_base + scenario for scenario in range(circumstances)]
    if set(train_seeds).intersection(heldout):
        raise RuleCurriculumError("training and evaluation scenario seeds overlap")
    result = learner.train(
        request.build,
        episodes=count, seeds=train_seeds,
    )
    if result.updates <= 0:
        raise RuleCurriculumError("no real learning updates were committed")
    evaluation = learner.evaluate(
        request.build,
        heldout_seeds=heldout, baseline_snapshot=previous,
    )
    details = evaluation.as_dict()
    records = []
    for i,row in enumerate(plan["scenarios"]):
        records.append({
            "scenario_id": row["scenario_id"],
            "source_digest": hashlib.sha256(json.dumps(
                row["source"], sort_keys=True, separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")).hexdigest(),
            "train_seed_count": episodes_per_scenario,
            "heldout_seed": heldout[i],
            "heldout_return_difference": details["episodes"][i]["return_difference"],
            "heldout_candidate_return": details["episodes"][i]["candidate"]["return"],
            "heldout_baseline_return": details["episodes"][i]["baseline"]["return"],
            "heldout_trace_digest": details["episodes"][i]["candidate"]["trace_digest"],
        })
    record = {
        "schema_version": "skeleton.game_builder.ai_rule_policy_candidate.v1",
        "candidate_status": "trained_not_promoted",
        "plan": plan,
        "environment_spec": spec.as_dict(),
        "environment_request_digest": request.digest,
        "training_algorithm": "measured_tabular_q_learning",
        "policy_snapshot": learner.snapshot(),
        "actual_policy_updates": result.updates,
        "trained_episodes": count,
        "training_episode_evidence": [
            {
                "seed": trace["seed"], "trace_digest": trace["trace_digest"],
                "environment_digest": trace["environment"]["environment_digest"],
            }
            for trace in result.traces
        ],
        "evaluation": details,
        "evaluation_by_circumstance": records,
        "candidate_improvement_claimed": False,
        "production_neural_weights_modified": False,
        "original_engine_rules_persistently_modified": False,
        "automatic_policy_promotion": False,
    }
    neural_sha = None
    if neural_corpus_output is not None:
        from skeleton.ai.training.jeeves_studio_rule_corpus import (
            build_rule_training_corpus, publish_rule_training_corpus,
        )
        if Path(neural_corpus_output).expanduser().absolute() == Path(output).expanduser().absolute():
            raise RuleCurriculumError("candidate and neural corpus cannot share a file path")
        examples = []
        # One actual witnessed training episode for every distinct scenario.
        # This keeps the trainer budget bounded and preserves the disjoint
        # independent heldout episodes (never exported for optimization).
        for trace in result.traces[:circumstances]:
            scenario = plan["scenarios"][trace["seed"] % circumstances]
            examples.append({
                "scenario_id": scenario["scenario_id"],
                "seed": trace["seed"],
                "actions": [row["action"] for row in trace["transitions"]],
            })
        corpus = build_rule_training_corpus(
            plan, examples, authorized=authorized, rights_cleared=rights_cleared,
        )
        neural_sha = publish_rule_training_corpus(neural_corpus_output, corpus)
    try:
        sha = _write_candidate(output, record)
    except BaseException:
        if neural_sha is not None:
            Path(neural_corpus_output).expanduser().absolute().unlink(missing_ok=True)
        raise
    return {
        "candidate": str(Path(output).expanduser().absolute()),
        "candidate_sha256": sha,
        "neural_training_corpus": (
            None if neural_corpus_output is None
            else str(Path(neural_corpus_output).expanduser().absolute())
        ),
        "neural_corpus_sha256": neural_sha,
        "rule_plan_digest": plan["digest"],
        "editor": base_source["editor"],
        "circumstances": circumstances,
        "episodes": count,
        "actual_q_updates": result.updates,
        "heldout_seed_count": len(heldout),
        "heldout_mean_return_difference": details["mean_return_difference"],
        "per_circumstance_evaluation": records,
        "model_promotion": "not_authorized",
        "production_neural_weights_modified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--editor", help="build a default original-game source")
    parser.add_argument("--source-file", type=Path,
                        help="prefer an exact saved studio session.json source")
    parser.add_argument("--settings-json", help="bounded JSON editor settings")
    parser.add_argument("--actions", nargs="+")
    parser.add_argument("--proposals", type=Path, required=True,
                        help="reviewed AI-generated JSON proposal list")
    parser.add_argument("--output", type=Path, required=True,
                        help="new private candidate path; never an active policy")
    parser.add_argument("--neural-corpus-output", type=Path,
                        help="optional replay-verified multi-rule input for checkpoint candidate training")
    parser.add_argument("--episodes-per-scenario", type=int, default=4)
    parser.add_argument("--max-steps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--authorized", action="store_true")
    parser.add_argument("--rights-cleared", action="store_true")
    args = parser.parse_args(argv)
    if (args.source_file is None) == (args.editor is None):
        parser.error("choose exactly one --source-file or --editor")
    if args.source_file is None:
        settings = json.loads(args.settings_json) if args.settings_json else None
        base = make_studio_source(
            args.editor, settings,
            actions=tuple(args.actions) if args.actions else None,
        )
    else:
        if args.settings_json or args.actions:
            parser.error("saved source is already bound to its actions and editor settings")
        base = parse_studio_source(_read_json(args.source_file, limit=131072))
    data = _read_json(args.proposals, limit=MAX_BATCH_BYTES)
    if type(data) is not dict or set(data) != {"schema_version", "proposals"} or (
            data["schema_version"] != "skeleton.game_builder.ai_rule_batch.v1"):
        raise RuleCurriculumError("exact JSON AI rule proposal batch required")
    result = train_rule_curriculum(
        base_source=base, proposals=data["proposals"], output=args.output,
        authorized=args.authorized, rights_cleared=args.rights_cleared,
        seed=args.seed, episodes_per_scenario=args.episodes_per_scenario,
        max_steps=args.max_steps,
        neural_corpus_output=args.neural_corpus_output,
    )
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
