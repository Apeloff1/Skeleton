#!/usr/bin/env python3
"""Audit whether a 30-game / 10-live-lane study is locally ready, without booting ROMs."""
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
    from skeleton.jeeves.game_comparison_readiness import inspect_game_comparison_readiness
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, REGISTRY_ENV

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True)
    parser.add_argument("--registry",type=Path,required=True)
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--deep-hash",action="store_true",
                        help="Read and SHA-256 all declared local disc/media files; can take substantial disk I/O")
    parser.add_argument("--probe-sandbox",action="store_true",
                        help="Actually launch a minimal bwrap sandbox containing only /usr/bin/true; no ROM or model")
    args=parser.parse_args(argv)
    try:
        if args.registry.is_symlink() or args.output_dir.is_symlink():
            raise ValueError("Core registry/output path cannot be symlinked")
        registry_path=args.registry.resolve(strict=True)
        registry=GameEmulatorRegistry(registry_path)
        os.environ[REGISTRY_ENV]=str(registry_path)
        if GameEmulatorRegistry.from_environment().registry_digest!=registry.registry_digest:
            raise ValueError("Operator core registry was changed before readiness check")
        model=_read_json_file(args.manifest,MAX_MANIFEST_BYTES)
        report=inspect_game_comparison_readiness(
            model,deep_hash=args.deep_hash,probe_sandbox=args.probe_sandbox,registry=registry,
        )
        out=args.output_dir.resolve()
        out.mkdir(parents=True,exist_ok=True)
        destination=out/(report["study_id"]+".readiness.json")
        _atomic_write(destination,json.dumps(report,indent=2,sort_keys=True,allow_nan=False).encode())
        source_prepared=sum(
            b["source_and_core_admitted"] and b["disk_issue"] is None
            for b in report["cohorts"]
        )
        prepared=sum(
            b["ready_for_simultaneous_live_desk"]
            for b in report["cohorts"]
        )
        print(json.dumps({
            "status":"operator_comparison_source_preflight_completed_no_gameplay_executed",
            "study_id":report["study_id"],
            "games":report["game_count"],
            "preflight_admitted_games":report["game_preflight_pass_count"],
            "source_preflight_cohorts":source_prepared,
            "ready_study_cohorts":prepared,
            "host_runtime_blockers":report["host_runtime"]["blockers"],
            "sandbox_probe":report["host_runtime"]["sandbox_probe"],
            "total_study_cohorts":len(report["cohorts"]),
            "full_disc_hash_checked":args.deep_hash,
            "report":str(destination),
            "actual_native_gameplay_verified":False,
            "model_weights_changed":False,
        },indent=2))
        return 0 if prepared==len(report["cohorts"]) else 3
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({"status":"comparison_operator_preflight_rejected",
                          "type":type(exc).__name__,"reason":str(exc)[:240]}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
