#!/usr/bin/env python3
"""Launch an explicitly authorized local native multi-emulator comparison desk.

Opens exactly one 30-game study cohort (2–10 live lanes) and serves a
dual-screen browser desk on 127.0.0.1 only. Does not download ROMs/cores,
silently train models or expose a network/public remote-control surface.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main(argv: list[str] | None = None) -> int:
    from scripts.compare_game_study import _read_json_file
    from skeleton.jeeves.game_comparison_schema import MAX_MANIFEST_BYTES,validate_study
    from skeleton.jeeves.game_comparison_live import LiveComparison
    from skeleton.jeeves.game_comparison_live_http import LocalComparisonServer
    from skeleton.jeeves.game_comparison_host_preflight import inspect_native_host_runtime
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry,REGISTRY_ENV

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True,
                        help="Previously authored study manifest with 2–30 source-pinned games")
    parser.add_argument("--registry",type=Path,required=True,
                        help="Exact approved local libretro core registry")
    parser.add_argument("--batch",type=int,required=True,
                        help="One selected <=10-game study cohort; 0-based")
    parser.add_argument("--game",action="append",
                        help="Optional game ID from the cohort; repeat 2–10 times to reduce resource use")
    parser.add_argument("--rights-acknowledged",action="store_true",
                        help="Confirm operator is allowed to run all included game media locally")
    parser.add_argument("--max-steps",type=int,default=4096,
                        help="1–4096 actual native input steps per lane for the entire desk lifetime")
    parser.add_argument("--timeout-seconds",type=float,default=5.0)
    parser.add_argument("--port",type=int,default=8765,
                        help="Local-only port 0–65535; 0 allocates a free ephemeral port")
    parser.add_argument("--idle-seconds",type=int,default=900,
                        help="Shut down live native workers after 60–3600 inactive seconds")
    args=parser.parse_args(argv)
    if not args.rights_acknowledged:
        parser.error("Native play requires explicit --rights-acknowledged; no source-rights certificate is inferred")
    try:
        host=inspect_native_host_runtime(probe_sandbox=True)
        if not host["native_launch_preflight_passed"]:
            names=", ".join(finding["code"] for finding in host["blockers"])
            raise ValueError("Native host sandbox preflight failed: "+names)
        if args.registry.is_symlink():
            raise ValueError("Core registry cannot be a symlink")
        pinned=args.registry.resolve(strict=True)
        registry=GameEmulatorRegistry(pinned)
        os.environ[REGISTRY_ENV]=str(pinned)
        if GameEmulatorRegistry.from_environment().registry_digest!=registry.registry_digest:
            raise ValueError("Approved core registry changed before operator launch")
        study=validate_study(_read_json_file(args.manifest,MAX_MANIFEST_BYTES))
        with LiveComparison(
            study,batch_index=args.batch,game_ids=args.game,
            max_steps=args.max_steps,timeout_seconds=args.timeout_seconds,
        ) as live:
            server=LocalComparisonServer(live,args.port,args.idle_seconds)
            monitor=threading.Thread(target=server.monitor_idle,daemon=True)
            monitor.start()
            try:
                print(json.dumps({
                    "status":"operator_local_native_live_comparison_running",
                    "url":"http://127.0.0.1:"+str(server.server_port)+"/",
                    "study_id":study["study_id"],"selected_batch":args.batch,
                    "active_native_emulator_lanes":len(live._lanes),
                    "lifetime_steps_per_game":args.max_steps,
                    "idle_shutdown_seconds":args.idle_seconds,
                    "physical_hardware_layout_verified":False,
                    "production_model_weights_changed":False,
                    "network_interface":"127.0.0.1 only",
                    "native_host_preflight_sha256":host["host_preflight_sha256"],
                    "bwrap_syscall_probe_passed":host["sandbox_probe"]["passed"],
                    "note":"This process must remain running for browser controls to work. No internet endpoints are opened.",
                },indent=2),flush=True)
                server.serve_forever(poll_interval=.25)
            finally:
                server.stopping.set()
                server.server_close()
                live.close()
        return 0
    except KeyboardInterrupt:
        return 130
    except (ValueError,OSError,RuntimeError) as exc:
        print(json.dumps({
            "status":"native_live_studio_rejected",
            "error_type":type(exc).__name__,
            "message":str(exc)[:240],
        }),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
