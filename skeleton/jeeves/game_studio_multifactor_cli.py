"""Operator-admitted multifactor interactive-world optimization.

Designs cross-factor pairs and triples from actual engine-validated controls,
runs source-verifiable ablations and optionally derives real local tabular-Q
candidates with independent holdout evaluations. No invented music, image,
body-language sensor, or neural-transformer weight-training claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .game_studio_environment import make_studio_source
from .game_studio_multifactor import (
    execute_multifactor_scenarios, multifactor_capabilities,
    plan_multifactor_scenarios,
)
from .game_studio_rule_training_cli import _read_json, _write_candidate


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    choice=parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--editor")
    choice.add_argument("--source-file",type=Path)
    parser.add_argument("--settings-json")
    parser.add_argument("--interaction-order",type=int,choices=(2,3),default=3)
    parser.add_argument("--axis-offset",type=int,default=0)
    parser.add_argument("--scenarios",type=int,default=8)
    parser.add_argument("--steps",type=int,default=4)
    parser.add_argument("--seed",type=int,default=11)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--plan-only",action="store_true")
    parser.add_argument("--train-local-q",action="store_true")
    parser.add_argument("--authorized",action="store_true")
    parser.add_argument("--rights-cleared",action="store_true")
    args=parser.parse_args(argv)
    if args.source_file is not None:
        if args.settings_json:
            parser.error("cannot change a pinned original game source silently")
        source=_read_json(args.source_file,limit=131072)
    else:
        settings=json.loads(args.settings_json) if args.settings_json else None
        source=make_studio_source(args.editor,settings)
    if not args.plan_only and (not args.authorized or not args.rights_cleared):
        parser.error("executing real-world learning scenarios needs explicit source rights and operator approval")
    if args.plan_only and args.train_local_q:
        parser.error("planning alone cannot claim real Q parameter training")
    if args.plan_only:
        report=plan_multifactor_scenarios(
            source,interaction_order=args.interaction_order,
            max_scenarios=args.scenarios,axis_offset=args.axis_offset,
        )
    else:
        report=execute_multifactor_scenarios(
            source,interaction_order=args.interaction_order,
            max_scenarios=args.scenarios,axis_offset=args.axis_offset,
            steps=args.steps,seed=args.seed,
            train=args.train_local_q,authorized=args.authorized,
            rights_cleared=args.rights_cleared,
        )
    sha=_write_candidate(args.output,report)
    result={
        "path":str(args.output.expanduser().absolute()),
        "sha256":sha,
        "editor":report["editor"],
        "scenario_count":len(report["scenarios"] if args.plan_only
                             else report["experiments"]),
        "training_enabled":bool(args.train_local_q),
        "measured_local_q_updates":(
            0 if args.plan_only else report["actual_q_weight_updates"]
        ),
        "production_neural_weights_modified":False,
        "automatic_promotion":False,
    }
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
