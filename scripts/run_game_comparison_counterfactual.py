#!/usr/bin/env python3
"""Run actual matched A/B native controller experiments across 2–10 games.

One input action is altered at an explicit step, and both arms are re-run
in 2–3 fresh approved sandboxed workers each. This never automatically trains
or promotes model weights.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main(argv:list[str]|None=None)->int:
    from scripts.compare_game_study import _read_json_file,_atomic_write
    from skeleton.jeeves.game_comparison_schema import MAX_MANIFEST_BYTES
    from skeleton.jeeves.game_comparison_counterfactual import (
        run_counterfactual_input_study,
    )
    from skeleton.jeeves.game_comparison_host_preflight import inspect_native_host_runtime
    from skeleton.ai.webcrawler.dragon_comparative_game_bridge import export_dragon_counterfactual_review
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry,REGISTRY_ENV

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--registry",type=Path,required=True)
    parser.add_argument("--game",action="append",required=True,
                        help="Exactly 2–10 games from the source study, each with a source-rights receipt")
    parser.add_argument("--step",type=int,required=True)
    parser.add_argument("--replacement",required=True,
                        help="Different, native-device-compatible libretro input action")
    parser.add_argument("--repeats",type=int,default=2)
    parser.add_argument("--rights-acknowledged",action="store_true")
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(argv)
    if not args.rights_acknowledged:
        parser.error("Actual native gameplay requires explicit --rights-acknowledged")
    try:
        if args.registry.is_symlink() or args.manifest.is_symlink() or args.output_dir.is_symlink():
            raise ValueError("Counterfactual study cannot accept symlinked source or output roots")
        host=inspect_native_host_runtime(probe_sandbox=True)
        if not host["native_launch_preflight_passed"]:
            raise ValueError("Native worker prerequisites denied: "+",".join(
                b["code"] for b in host["blockers"]))
        path=args.registry.resolve(strict=True)
        registry=GameEmulatorRegistry(path)
        os.environ[REGISTRY_ENV]=str(path)
        if GameEmulatorRegistry.from_environment().registry_digest!=registry.registry_digest:
            raise ValueError("Approved registry differs from exact counterfactual authority")
        report=run_counterfactual_input_study(
            _read_json_file(args.manifest,MAX_MANIFEST_BYTES),
            game_ids=args.game,step=args.step,
            replacement_action=args.replacement,
            repeats=args.repeats,registry=registry,
        )
        output=args.output_dir.resolve()
        output.mkdir(parents=True,exist_ok=True)
        artifact=output/(report["source_study_id"]+"_controlled_input.json")
        _atomic_write(
            artifact,json.dumps(report,sort_keys=True,indent=2,allow_nan=False).encode(),
        )
        intake=export_dragon_counterfactual_review(report)
        dragon_report=output/(report["source_study_id"]+"_counterfactual_dragon_review.json")
        _atomic_write(
            dragon_report,
            json.dumps(intake,sort_keys=True,indent=2,allow_nan=False).encode(),
        )
        print(json.dumps({
            "status":"actual_bounded_counterfactual_emulator_experiments_completed",
            "games":report["game_count"],
            "fresh_native_runs":report["fresh_native_runs_completed"],
            "same_input_except_one_action":True,
            "result":str(artifact),
            "dragon_review_candidates":str(dragon_report),
            "production_llm_weights_changed":False,
            "game_mechanics_proven":False,
            "heldout_improvement_verified":False,
        },indent=2))
        return 0
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({"status":"counterfactual_native_experiment_rejected",
                          "type":type(exc).__name__,"reason":str(exc)[:280]}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
