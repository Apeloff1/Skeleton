"""Ten-run scrutinized mirror-room curriculum for local Jeeves game Q-policy.

Replay-priority ranking uses real *audited game outcomes*, not hypothetical
measurements or fabricated independent multispectral sensors. Each of ten
spectator-style exploratory runs is independently source-replayed under ten
audits; these seeds then direct ten actual Q-learning episodes and separate
held-out evaluation. This is not Dreamer, PLR's TD-error formula, production
model self-modification, physical spectra, or unapproved model promotion.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from .game_learning import GameLearningConfig, GamePolicyLearner
from .game_learning_parallel import GameEnvironmentRequest
from .game_studio_environment import (
    make_studio_source, parse_studio_source, studio_request_tree,
)
from .game_studio_scenario_lab import ANGLES, mirrored_simulations
from .game_studio_multispectral import BANDS
from .game_studio_rule_training_cli import _read_json, _write_candidate


class MirrorTrainingError(ValueError):
    """Multi-run training source, budgets, replay identity or scrutiny failed."""


def measured_training_priority(lane: dict) -> dict:
    """Rank real replay evidence without treating it as learned TD error."""
    proof=lane.get("multispectral")
    if (type(proof) is not dict or proof.get("passed_count")!=10
            or lane.get("audit_passed") is not True
            or set(proof.get("spectral_channels",{}))!=set(BANDS)):
        raise MirrorTrainingError("an unverified mirror cannot enter training priority")
    productive=lane["productive_state_changes"]
    distinct=max(0,lane["unique_gameplay_states"]-1)
    rejected=lane["rejected_actions"]
    cost=max(1,lane["replayed_action_applications"])
    # Actual state novelty yields positive value; invalid spam costs priority.
    # Cost penalty matters because source replay is superlinear with steps.
    score=round(
        5*productive + 2*distinct - 3*rejected
        + 100*productive/cost
        + min(4,abs(lane["total_reward"]))
        - cost/32,
        6,
    )
    return {
        "angle":lane["angle"], "seed":lane["seed"],
        "source_digest":lane["source_digest"],
        "multispectral_audit_digest":proof["digest"],
        "state_trajectory_digest":lane["gameplay_transition_states_digest"],
        "priority":score,
        "actual_gameplay_steps":lane["steps"],
        "actual_productive_changes":productive,
        "invalid_actions":rejected,
        "real_td_error_measured":False,
        "independent_physical_sensors_used":False,
    }


def train_ten_run_multispectral(
    *, source: dict, output: Path, authorized: bool, rights_cleared: bool,
    seed: int=0, max_steps: int=8,
) -> dict:
    if authorized is not True or rights_cleared is not True:
        raise PermissionError("ten-run original game training needs operator and source rights approval")
    if (type(seed) is not int or not 0<=seed<=2**31-100020
            or type(max_steps) is not int or not 1<=max_steps<=24):
        raise MirrorTrainingError("ten-run source and episode budgets exceeded")
    original=parse_studio_source(source)
    exploratory=mirrored_simulations(
        original,seed=seed,steps=max_steps,angles=ANGLES,workers=4,
    )
    if len(exploratory["lanes"])!=10 or exploratory["scrutiny_checked_runs"]!=10:
        raise MirrorTrainingError("all ten independently audited source runs are required")
    priority=[measured_training_priority(row) for row in exploratory["lanes"]]
    priority.sort(key=lambda item:(-item["priority"],item["angle"],item["seed"]))
    training_seeds=[row["seed"] for row in priority]
    heldout=[seed+100000+i for i in range(3)]
    if set(training_seeds).intersection(heldout):
        raise MirrorTrainingError("training and independent heldout seed collision")
    request=GameEnvironmentRequest(
        "studio:"+original["editor"],kind="studio",
        tree=studio_request_tree(original),max_steps=max_steps,
    )
    env=request.build()
    try:
        spec=env.spec
    finally:
        env.close()
    learner=GamePolicyLearner(
        spec,GameLearningConfig(
            seed=seed,max_episodes=10,max_updates=10*max_steps,
        ),
        policy_id="ten-run-multispectral:"+original["editor"]+":"+str(seed),
        source_lineage={
            "origin":"independently_audited_original_game_ten_mirrors",
            "rights_acknowledged":True,
            "admitted_game_source_digest":exploratory["source_digest"],
            "ten_passes_per_exploratory_run":True,
            "derived_numeric_multispectral_only":True,
        },
    )
    before=learner.snapshot()
    trained=learner.train(request.build,episodes=10,seeds=training_seeds)
    if trained.updates<=0:
        raise MirrorTrainingError("no actual game action policy updates occurred")
    evaluation=learner.evaluate(
        request.build,heldout_seeds=heldout,baseline_snapshot=before,
    ).as_dict()
    record={
        "schema_version":"skeleton.game_builder.ten_run_multispectral_candidate.v1",
        "status":"candidate_not_promoted",
        "editor":original["editor"],
        "source_digest":exploratory["source_digest"],
        "mirror_room_digest":exploratory["digest"],
        "training_request_digest":request.digest,
        "ten_spectator_scenarios_audited":10,
        "scrutiny_passes_confirmed":100,
        "real_spectral_sensor_inputs":False,
        "analysis_band_names":list(BANDS),
        "priority_algorithm":"measured_state_change_and_replay_cost_not_plr_td_error",
        "measured_training_priorities":priority,
        "actual_q_training_episode_seeds":training_seeds,
        "actual_q_training_episodes":len(trained.traces),
        "actual_q_updates":trained.updates,
        "training_trace_digests":[t["trace_digest"] for t in trained.traces],
        "independent_heldout_seeds":heldout,
        "evaluation":evaluation,
        "policy_snapshot":learner.snapshot(),
        "production_neural_weights_modified":False,
        "automatic_promotion":False,
        "generalization_or_sales_improvement_certified":False,
    }
    digest=_write_candidate(output,record)
    return {
        "candidate":str(Path(output).expanduser().absolute()),
        "candidate_sha256":digest,
        "editor":original["editor"],
        "audited_mirror_runs":10,
        "audits_passed":100,
        "actual_q_episodes":len(trained.traces),
        "actual_q_updates":trained.updates,
        "independent_heldout_seed_count":len(heldout),
        "heldout_mean_return_difference":evaluation["mean_return_difference"],
        "multispectral_type":"ten_source_derived_numeric_gameplay_channels",
        "promotion_authorized":False,
        "production_neural_weights_modified":False,
    }


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine")
    parser.add_argument("--source-file",type=Path)
    parser.add_argument("--settings-json")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seed",type=int,default=0)
    parser.add_argument("--max-steps",type=int,default=8)
    parser.add_argument("--authorized",action="store_true")
    parser.add_argument("--rights-cleared",action="store_true")
    args=parser.parse_args(argv)
    if (args.engine is None)==(args.source_file is None):
        parser.error("choose exactly one original engine or canonical source")
    if args.source_file is not None:
        if args.settings_json:
            parser.error("saved source cannot be silently reconfigured")
        source=_read_json(args.source_file,limit=131072)
    else:
        settings=json.loads(args.settings_json) if args.settings_json else None
        source=make_studio_source(args.engine,settings)
    result=train_ten_run_multispectral(
        source=source,output=args.output,authorized=args.authorized,
        rights_cleared=args.rights_cleared,seed=args.seed,
        max_steps=args.max_steps,
    )
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
