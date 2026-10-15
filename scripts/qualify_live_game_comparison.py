#!/usr/bin/env python3
"""Verify native live-controller evidence and re-run one epoch in fresh workers.

This is explicit operator work only. It cannot fetch ROMs or BIOS, promote
weights, assert content rights, or claim accuracy from replay consistency.
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
    from scripts.compare_game_study import _atomic_write,_read_json_file
    from skeleton.jeeves.game_comparison_schema import MAX_MANIFEST_BYTES,digest,validate_study
    from skeleton.jeeves.game_comparison_live_evidence import verify_live_evidence
    from skeleton.jeeves.game_comparison_media import prepare_comparison_media
    from skeleton.jeeves.game_emulator_qualification import run_emulator_qualification
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry,REGISTRY_ENV

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",type=Path,required=True,help="Local authenticated session's exported evidence JSON")
    parser.add_argument("--output-dir",type=Path,required=True)
    parser.add_argument("--manifest",type=Path,help="Required with actual replay; original source-pinned study manifest")
    parser.add_argument("--registry",type=Path,help="Required with actual replay; approved installed libretro core registry")
    parser.add_argument("--game",help="Actual game ID to replay in new native worker processes")
    parser.add_argument("--episode",type=int,default=0,help="Reset epoch index, starting with zero")
    parser.add_argument("--runs",type=int,default=3,help="2–10 fresh native replay workers")
    parser.add_argument("--rights-acknowledged",action="store_true",
                        help="Explicit operator rights assertion needed before replaying ROM content")
    args=parser.parse_args(argv)
    try:
        if args.evidence.is_symlink() or args.output_dir.is_symlink():
            raise ValueError("No symlinked live evidence or report output")
        packet=_read_json_file(args.evidence,5*1024*1024)
        verified=verify_live_evidence(packet)
        path=args.output_dir.resolve()
        path.mkdir(parents=True,exist_ok=True)
        _atomic_write(path/"live_session_verified.json",
                      json.dumps(verified,sort_keys=True,indent=2,allow_nan=False).encode())
        if args.game is None:
            if args.registry is not None or args.manifest is not None or args.rights_acknowledged:
                raise ValueError("Native replay needs --game, --manifest, --registry and --rights-acknowledged")
            print(json.dumps({
                "status":"offline_native_evidence_chains_verified",
                "game_count":verified["game_count"],
                "native_input_steps":verified["total_real_reported_native_steps"],
                "real_gameplay_replayed":False,
                "verification":str(path/"live_session_verified.json"),
            },indent=2))
            return 0
        if not args.rights_acknowledged or args.manifest is None or args.registry is None:
            raise ValueError("Native mirror replay requires explicit game, manifest, registry and rights acknowledgment")
        if args.registry.is_symlink():
            raise ValueError("Native core registry must not be a symlink")
        selected=next((x for x in verified["games"] if x["game_id"]==args.game),None)
        if selected is None:
            raise ValueError("Requested replay game is absent from actual verified live evidence")
        tapes=selected["replayable_controller_tapes"]
        if type(args.episode) is not int or not 0<=args.episode<len(tapes):
            raise ValueError("Requested native reset epoch does not exist")
        tape=tapes[args.episode]
        if not 1<=len(tape)<=64:
            raise ValueError("The selected epoch has no actions or exceeds 64 native replay inputs; use another epoch or a separately bounded partition")
        model=validate_study(_read_json_file(args.manifest,MAX_MANIFEST_BYTES))
        if digest(model)!=packet["study_digest"]:
            raise ValueError("Native replay study authority differs from verified live recording")
        game=next(g for g in model["games"] if g["id"]==args.game)
        core_path=args.registry.resolve(strict=True)
        registry=GameEmulatorRegistry(core_path)
        os.environ[REGISTRY_ENV]=str(core_path)
        if registry.registry_digest!=packet["registry_digest"] or (
            GameEmulatorRegistry.from_environment().registry_digest!=registry.registry_digest
        ):
            raise ValueError("Approved native core registry changed since live observation")
        content_kwargs,content_sha256=prepare_comparison_media(game)
        if content_sha256!=packet["lanes"][args.game]["source_media_sha256"]:
            raise ValueError("Actual replay ROM or disc bundle differs from original pinned source identity")
        replay=run_emulator_qualification(
            game["target_id"],core_id=game["core_id"],
            expected_registry_digest=registry.registry_digest,
            controller_tape=tape,**content_kwargs,
            runs=args.runs,seed=game["seed"],
            frames_per_step=game["frames_per_step"],
            controller_devices=game["controller_devices"],
            timeout_seconds=5.0,
            rights_evidence_digest=game["rights_evidence_digest"],
            include_traces=False,
        )
        events=packet["lanes"][args.game]["native_events"]
        epoch=0
        original=[]
        for event in events:
            if event["event_kind"]=="native_reset":
                epoch+=1
            elif epoch==args.episode:
                original.append(event["receipt"])
        if len(original)!=len(tape):
            raise ValueError("Original native step receipt count differs from controller epoch")
        last=original[-1]
        comparison=[{
            "run":row["run"],
            "same_final_video_sha256":row["last_video_sha256"]==last["frame_sha256"],
            "same_final_pcm_sha256":row["last_audio_sha256"]==last["pcm_sha256"],
            "fresh_worker_process_requested":True,
        } for row in replay["run_receipts"]]
        result={
            "schema_version":"skeleton.game.live_epoch_replay_qualification.v1",
            "source_verified_live_receipt":verified["verification_sha256"],
            "game_id":args.game,"epoch":args.episode,
            "input_steps":len(tape),
            "source_rom_identity_sha256":content_sha256,
            "original_last_frame_sha256":last["frame_sha256"],
            "original_last_pcm_sha256":last["pcm_sha256"],
            "replay_audit":replay,
            "compared_to_original_live_frame":comparison,
            "hardware_accuracy_proven":False,
            "source_rights_independently_verified":False,
            "llm_training_or_weight_promotion":False,
        }
        result["qualification_sha256"]=digest(result)
        dest=path/(args.game+"_episode_"+str(args.episode)+"_native_replay.json")
        _atomic_write(dest,json.dumps(result,sort_keys=True,indent=2,allow_nan=False).encode())
        print(json.dumps({
            "status":"independent_native_replay_qualification_completed",
            "game_id":args.game,"epoch":args.episode,
            "fresh_native_worker_runs":replay["runs_completed"],
            "all_replays_match_original_last_frame":all(
                r["same_final_video_sha256"] and r["same_final_pcm_sha256"]
                for r in comparison),
            "report":str(dest),
            "model_weights_changed":False,
        },indent=2))
        return 0
    except (ValueError,OSError,RuntimeError,StopIteration) as exc:
        print(json.dumps({"status":"live_replay_qualification_rejected",
                          "type":type(exc).__name__,
                          "reason":str(exc)[:240]}),file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
