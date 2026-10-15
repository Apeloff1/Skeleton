#!/usr/bin/env python3
"""Plan/execute/resume a bounded boomerang comparative-game training curriculum.

By default, PLAN ONLY: no native cores, ROMs or training are touched.
--execute additionally requires source rights, approved local cores, trusted
Linux bubblewrap and an explicit ceiling on native worker executions.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
MAX_REPORT=24*1024*1024


def _output(destination:Path,name:str,payload:object)->None:
    from scripts.compare_game_study import _atomic_write
    output=destination/name
    if output.is_symlink():
        raise ValueError("Boomerang study output may not replace symlinked files")
    data=json.dumps(payload,indent=2,sort_keys=True,allow_nan=False).encode()
    if len(data)>MAX_REPORT:
        raise ValueError("Bounded boomerang evidence report exceeds 24 MiB")
    _atomic_write(output,data)


def main(argv:list[str]|None=None)->int:
    from scripts.compare_game_study import _read_json_file
    from skeleton.jeeves.game_comparison_schema import MAX_MANIFEST_BYTES
    from skeleton.jeeves.game_comparison_host_preflight import inspect_native_host_runtime
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry,REGISTRY_ENV
    from skeleton.jeeves.game_comparison_counterfactual import run_counterfactual_input_study
    from skeleton.jeeves.game_comparison_boomerang import (
        plan_comparison_boomerang,verify_boomerang_plan,
        make_boomerang_progress,
    )
    from skeleton.jeeves.game_comparison_counterfactual_viewer import render_counterfactual_game_dashboard

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--game",action="append",required=True)
    parser.add_argument("--treatments",type=int,default=3,help="1–8 distinct single-action interventions")
    parser.add_argument("--revisit-rounds",type=int,default=2,
                        help="0–2 deterministic boomerang reinspection rounds")
    parser.add_argument("--repeats",type=int,default=2,help="2–3 fresh native repeats of each arm")
    parser.add_argument("--candidate-action",action="append",
                        help="Explicit native-device-compatible interventions, unique and <=16")
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--execute",action="store_true",
                        help="Run the actual bounded native experiment queue; otherwise plan only")
    parser.add_argument("--registry",type=Path,help="Approved installed libretro registry; mandatory for execute")
    parser.add_argument("--rights-acknowledged",action="store_true",
                        help="Required for actual execution; must possess lawful local game media")
    parser.add_argument("--approve-native-runs",type=int,default=0,
                        help="Explicit positive per-run authorization cap, >= planned execution count")
    args=parser.parse_args(argv)
    try:
        if (args.manifest.is_symlink() or args.output_dir.is_symlink()
            or args.registry is not None and args.registry.is_symlink()):
            raise ValueError("Study input/approved core registry/output path cannot be symlinked")
        study=_read_json_file(args.manifest,MAX_MANIFEST_BYTES)
        plan=plan_comparison_boomerang(
            study,game_ids=args.game,treatments=args.treatments,
            revisit_rounds=args.revisit_rounds,repeats=args.repeats,
            candidate_actions=args.candidate_action,
        )
        verify_boomerang_plan(plan,study)
        folder=args.output_dir.resolve()
        folder.mkdir(parents=True,exist_ok=True)
        plan_path=folder/"boomerang_plan.json"
        if plan_path.exists():
            if plan_path.is_symlink():
                raise ValueError("Existing boomerang plan cannot be a symlink")
            prior=_read_json_file(plan_path,MAX_REPORT)
            if prior!=plan:
                raise ValueError("Existing study output belongs to a different bounded boomerang plan")
        _output(folder,"boomerang_plan.json",plan)
        if not args.execute:
            progress=make_boomerang_progress(plan,[])
            # Do not overwrite existing execution progress during read-only planning.
            if not (folder/"boomerang_progress.json").exists():
                _output(folder,"boomerang_progress.json",progress)
            print(json.dumps({
                "status":"plan_only_no_native_execution",
                "study_id":plan["source_study_id"],
                "scheduled_treatments":len(plan["schedule"]),
                "estimated_fresh_native_worker_runs":plan["estimated_fresh_native_worker_runs"],
                "plan":str(plan_path),
                "model_weights_changed":False,
            },indent=2))
            return 0
        estimate=plan["estimated_fresh_native_worker_runs"]
        if (not args.rights_acknowledged or args.registry is None
            or type(args.approve_native_runs) is not int
            or args.approve_native_runs<estimate):
            raise ValueError(
                "Native execution requires --rights-acknowledged, --registry and "
                "--approve-native-runs >= "+str(estimate)
            )
        host=inspect_native_host_runtime(probe_sandbox=True)
        if not host["native_launch_preflight_passed"]:
            raise ValueError("Native worker sandbox cannot launch: "+
                             ",".join(x["code"] for x in host["blockers"]))
        path=args.registry.resolve(strict=True)
        registry=GameEmulatorRegistry(path)
        os.environ[REGISTRY_ENV]=str(path)
        if GameEmulatorRegistry.from_environment().registry_digest!=registry.registry_digest:
            raise ValueError("Approved core registry diverged from live native authority")
        results=[]
        for task in plan["schedule"]:
            dest=folder/("native_trial_"+str(task["slot"]).zfill(3)+".json")
            if dest.is_symlink():
                raise ValueError("Saved native trial cannot be a symlink")
            if dest.exists():
                saved=_read_json_file(dest,MAX_REPORT)
                # Recomputed input/frame/PCM hashes are a required resume gate.
                make_boomerang_progress(plan,[*results,saved])
                result=saved
            else:
                result=run_counterfactual_input_study(
                    study,game_ids=task["game_ids"],
                    step=task["step"],
                    replacement_action=task["replacement_action"],
                    repeats=plan["repeats_per_arm"],registry=registry,
                )
                make_boomerang_progress(plan,[*results,result])
                _output(folder,dest.name,result)
                # Each completed treatment has a separate offline evidence UI.
                html=render_counterfactual_game_dashboard(result)
                _output_html=folder/("native_trial_"+str(task["slot"]).zfill(3)+".html")
                if _output_html.is_symlink():
                    raise ValueError("Native trial HTML cannot be a symlink")
                from scripts.compare_game_study import _atomic_write
                _atomic_write(_output_html,html.encode())
            results.append(result)
            progress=make_boomerang_progress(plan,results)
            _output(folder,"boomerang_progress.json",progress)
            print(json.dumps({
                "completed_treatment":task["slot"]+1,
                "total_treatments":len(plan["schedule"]),
                "round":task["round"],
                "source_evidence_sha256":result["result_sha256"],
                "progress_sha256":progress["progress_sha256"],
            }),flush=True)
        print(json.dumps({
            "status":"all_bounded_native_boomerang_experiments_completed",
            "study_id":plan["source_study_id"],
            "fresh_native_worker_runs":progress["fresh_native_worker_runs_completed"],
            "distinct_observed_signal_signatures":progress["novel_response_patterns_observed"],
            "progress_report":str(folder/"boomerang_progress.json"),
            "verified_human_gameplay_quality_improvement":False,
            "production_model_weights_changed":False,
        },indent=2))
        return 0
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({
            "status":"boomerang_curriculum_rejected_or_incomplete",
            "error_type":type(exc).__name__,
            "reason":str(exc)[:260],
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
