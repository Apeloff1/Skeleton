#!/usr/bin/env python3
"""Export the full 169-target core/installation/controller gap matrix (no ROM runs)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main(argv:list[str]|None=None)->int:
    from scripts.compare_game_study import _atomic_write
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry, REGISTRY_ENV
    from skeleton.jeeves.game_emulator_target_gap_matrix import (
        build_emulator_target_gap_matrix,render_emulator_gap_dashboard,
    )

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry",type=Path,
                        help="Optional operator-approved core manifest; unset uses environment or empty registry")
    parser.add_argument("--output-dir",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if args.output_dir.is_symlink() or (args.registry is not None and args.registry.is_symlink()):
            raise ValueError("Gap audit paths cannot be symlinks")
        if args.registry is not None:
            location=args.registry.resolve(strict=True)
            registry=GameEmulatorRegistry(location)
            os.environ[REGISTRY_ENV]=str(location)
            if GameEmulatorRegistry.from_environment().registry_digest!=registry.registry_digest:
                raise ValueError("Operator registry mutated during gap inventory")
        else:
            registry=GameEmulatorRegistry.from_environment()
        result=build_emulator_target_gap_matrix(registry=registry)
        destination=args.output_dir.resolve()
        destination.mkdir(parents=True,exist_ok=True)
        report=destination/"emulator_169_target_gaps.json"
        viewer=destination/"emulator_169_target_gaps.html"
        _atomic_write(report,json.dumps(result,indent=2,sort_keys=True,allow_nan=False).encode())
        _atomic_write(viewer,render_emulator_gap_dashboard(result).encode())
        print(json.dumps({
            "status":"hardware_emulator_coverage_audited_without_native_execution",
            "summary":result["summary"],
            "json_report":str(report),
            "offline_dashboard":str(viewer),
            "actual_native_roms_executed":0,
            "model_weights_changed":False,
        },indent=2))
        return 0
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({"status":"hardware_gap_audit_rejected",
                          "type":type(exc).__name__,"reason":str(exc)[:280]}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
