#!/usr/bin/env python3
"""Export and independently verify source-replayed Godot RPG dispatch.

prepare: cold audit native quest checkpoint, write one fixed data resource
and bind its exact file SHA-256 to the authorized scene settings. The scene
is explicitly selected and updated, but signed GDD is NEVER changed.
verify: rebuild the bundle from the journal and compare Godot's actual
runtime receipt after a subsequent headless/interactive engine run.
"""
from __future__ import annotations
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))
from scripts.run_game_frontier_capture import _operator_json
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal
from skeleton.jeeves.game_frontier_native_rpg_bridge import parse_native_rpg_pages
from skeleton.jeeves.game_frontier_native_engine_dispatch import (
    compile_native_godot_dispatch,canonical_dispatch_json,dispatch_file_sha256,
)


class GodotDispatchError(ValueError):
    pass


def _identities(args):
    gdd=bind_signed_gdd(_operator_json(args.signed_gdd))
    scene=_operator_json(args.scene_json)
    runtime=scene.get("native_capture")
    if (scene.get("schema")!="skeleton.game.frontier_godot_overlay.v1"
        or type(runtime) is not dict or runtime.get("enabled") is not True
        or runtime.get("gdd_digest")!=gdd.source_digest
        or runtime.get("candidate_digest")!=scene.get("origin_candidate_digest")
        or runtime.get("actor_id")!=args.actor_id):
        raise GodotDispatchError("signed GDD, candidate and controlled actor binding required")
    return gdd,scene,runtime


def _compile(args):
    gdd,scene,settings=_identities(args)
    raw_pages=_operator_json(args.event_pages_json)
    if raw_pages.get("source_actor_id",args.actor_id)!=args.actor_id:
        raise GodotDispatchError("page catalog actor differs from verified game actor")
    pages=parse_native_rpg_pages(raw_pages)
    graph=_operator_json(args.quest_graph_json)
    approvals=_operator_json(args.quest_approvals_json)
    checkpoint=_operator_json(args.checkpoint_json,limit=48*1024*1024)
    with FrameReceiptJournal(args.journal,gdd,track=args.track) as journal:
        native=journal.native_sample(0)
        if native is None or native.get("scene_candidate_digest")!=settings["candidate_digest"]:
            raise GodotDispatchError("native game scene evidence missing")
        stated=settings.get("actors")
        catalog=({x["id"]:x["source_digest"] for x in stated}
                 if stated is not None else
                 {settings["actor_id"]:settings["actor_asset_digest"]})
        if (len(catalog)!=(len(stated) if stated is not None else 1) or
            {a["id"]:a["source_digest"] for a in native["actors"]}!=catalog or
            args.actor_id not in catalog):
            raise GodotDispatchError("observed Godot actor catalog does not match scene")
        bundle=compile_native_godot_dispatch(
            journal,pages,graph,approvals,checkpoint,
            actor_id=args.actor_id,
            scene_candidate_digest=settings["candidate_digest"],
            max_frames=args.max_frames,
            frames_per_window=args.frames_per_window)
    return scene,bundle


def _write_new(path:Path,data:str)->None:
    if not path.parent.is_dir() or path.parent.is_symlink() or path.exists() or path.is_symlink():
        raise GodotDispatchError("Godot dispatch destination must be new and regular")
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _prepare(args):
    scene,bundle=_compile(args)
    expected_path=args.project/"frontier/data/scene.json"
    path=args.project/"frontier/data/native_gameplay_dispatch.json"
    if (not args.project.is_dir() or args.project.is_symlink()
        or args.scene_json.resolve()!=expected_path.resolve()
        or path.exists() or not expected_path.is_file()
        or expected_path.is_symlink()):
        raise GodotDispatchError("explicit existing Forge project with unused dispatch slot required")
    blob=canonical_dispatch_json(bundle)
    _write_new(path,blob)
    try:
        scene["native_capture"]["native_gameplay_dispatch"]={
            "schema":"skeleton.game.native_godot_dispatch_binding.v1",
            "file_sha256":dispatch_file_sha256(bundle)}
        # Updating this generated scene is an explicit operator action. Its
        # original GDD digest and candidate digest are preserved as source.
        temp=expected_path.with_suffix(".dispatch.tmp")
        _write_new(temp,json.dumps(scene,sort_keys=True,separators=(",",":"),
                                       allow_nan=False)+"\n")
        os.replace(temp,expected_path)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return {
        "operation":"prepare",
        "dispatch_path":str(path),
        "scene_json":str(expected_path),
        "dispatch_file_sha256":dispatch_file_sha256(bundle),
        "expected_actions":len(bundle["actions"]),
        "independent_cold_audit_digest":bundle["independent_cold_audit_digest"],
        "source_checkpoint_digest":bundle["verified_checkpoint_digest"],
        "authority":"explicit_operator_installed_local_godot_gameplay_commands",
    }


def _verify(args):
    scene,bundle=_compile(args)
    dispatch=args.project/"frontier/data/native_gameplay_dispatch.json"
    expected=dispatch_file_sha256(bundle)
    bound=scene["native_capture"].get("native_gameplay_dispatch",{})
    if (bound.get("file_sha256")!=expected or
        not dispatch.is_file() or dispatch.is_symlink() or
        sha256(dispatch.read_bytes()).hexdigest()!=expected or
        dispatch.read_bytes()!=canonical_dispatch_json(bundle).encode()):
        raise GodotDispatchError("Godot dispatch file or signed source binding changed")
    receipt=_operator_json(args.engine_receipt_json)
    expected_keys={
        "schema","dispatch_file_sha256","dispatch_receipt_digest",
        "signed_gdd_digest","scene_candidate_digest","actor_id",
        "source_through_frame","actions_applied","quests","flags",
        "presentation_cues","inventory","npc_emotions","visualized_npc_ids",
        "executed_action_trace","visualized_item_ids","cue_timeline_frame_index",
        "read_only_branch_options","authority",
    }
    allowed_cues={"show_dialogue","play_cutscene","play_music",
                  "spatial_audio","change_camera","inspect_instrument",
                  "trigger_impact_fx","trigger_foliage_fx"}
    expected_cues=[{
        "kind":entry["kind"],"cue":entry["value"],
        "source_frame":entry["frame"],"page_id":entry["page_id"],
    } for entry in bundle["actions"] if entry["kind"] in allowed_cues]
    if (type(receipt) is not dict or set(receipt)!=expected_keys
        or receipt["schema"]!="skeleton.game.godot_approved_dispatch_receipt.v1"
        or receipt["authority"]!="approved_gameplay_runtime_local_state_not_canonical_world_promotion"
        or receipt["dispatch_file_sha256"]!=expected
        or receipt["dispatch_receipt_digest"]!=bundle["receipt_digest"]
        or receipt["scene_candidate_digest"]!=bundle["scene_candidate_digest"]
        or receipt["signed_gdd_digest"]!=bundle["signed_gdd_digest"]
        or receipt["actor_id"]!=bundle["actor_id"]
        or receipt["source_through_frame"]!=bundle["source_through_frame"]
        or type(receipt["actions_applied"]) is not int
        or receipt["actions_applied"]!=len(bundle["actions"])
        or receipt["quests"]!=bundle["expected_quests"]
        or receipt["read_only_branch_options"]!=bundle["available_branch_options"]
        or receipt["flags"]!=bundle["expected_flags"]
        or receipt["inventory"]!=bundle["expected_inventory"]
        or receipt["npc_emotions"]!=bundle["expected_npc_emotions"]
        or receipt["visualized_npc_ids"]!=sorted(bundle["expected_npc_emotions"])
        or receipt["visualized_item_ids"]!=sorted(bundle["expected_inventory"])[:24]
        or receipt["presentation_cues"]!=expected_cues
        or receipt["cue_timeline_frame_index"]!=[c["source_frame"] for c in expected_cues]
        or receipt["executed_action_trace"]!=bundle["expected_action_trace"]):
        raise GodotDispatchError("actual Godot engine gameplay state does not match source replay")
    return {
        "operation":"verify","verified_engine_actions":len(bundle["actions"]),
        "verified_action_receipts":len(receipt["executed_action_trace"]),
        "verified_quest_count":len(receipt["quests"]),
        "verified_npc_reactions":len(receipt["visualized_npc_ids"]),
        "verified_inventory_visuals":len(receipt["visualized_item_ids"]),
        "verified_cue_count":len(expected_cues),
        "verified_cue_timeline_ticks":len(receipt["cue_timeline_frame_index"]),
        "dispatch_file_sha256":expected,
        "engine_gameplay_receipt_sha256":sha256(args.engine_receipt_json.read_bytes()).hexdigest(),
        "checkpoint_digest":bundle["verified_checkpoint_digest"],
        "authority":"actual_Godot_local_dispatch_receipt_rechecked_against_cold_native_replay",
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation",choices=("prepare","verify"))
    for option in ("signed-gdd","scene-json","journal","event-pages-json",
                   "quest-graph-json","quest-approvals-json","checkpoint-json",
                   "project"):
        parser.add_argument("--"+option,type=Path,required=True)
    parser.add_argument("--actor-id",default="hero")
    parser.add_argument("--track",default="production")
    parser.add_argument("--max-frames",type=int,default=4096)
    parser.add_argument("--frames-per-window",type=int,default=256)
    parser.add_argument("--engine-receipt-json",type=Path)
    args=parser.parse_args(argv)
    if (args.operation=="verify")!=(args.engine_receipt_json is not None):
        parser.error("engine receipt must be supplied exactly for independent verification")
    try:
        report=_prepare(args) if args.operation=="prepare" else _verify(args)
        print(json.dumps(report,sort_keys=True,separators=(",",":")))
        return 0
    except (ValueError,TypeError,KeyError,OSError,IndexError) as exc:
        print(f"Godot dispatch rejected: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
