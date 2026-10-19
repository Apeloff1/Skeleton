#!/usr/bin/env python3
"""Fixture-only approval selector for real Godot smoke quest replay.

A test fixture deliberately approves two precisely identified event pages
from a replay-verified native Godot journal. This is NOT production operator
authentication, a game save writer, or authorization of canonical world
mutations. The signed GDD and per-frame evidence are rechecked on replay.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))

from scripts.run_game_frontier_capture import _operator_json
from skeleton.jeeves.game_frontier_frame_coherence import bind_signed_gdd
from skeleton.jeeves.game_frontier_native_quest_session import (
    authored_page_digest,parse_native_quest_graph,simulate_native_quest_session,
)
from skeleton.jeeves.game_frontier_native_rpg_bridge import (
    parse_native_rpg_pages,evaluate_native_rpg_timeline,
)
from skeleton.jeeves.game_frontier_receipt_journal import FrameReceiptJournal


def _digest(payload: dict) -> str:
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def select_fixture_approvals(
    timeline: dict, *, actor_id: str, track: str, gdd_digest: str,
    pages_digest: str, graph_digest: str,
    begin_page: str="begin_sky_trial",
    complete_page: str="complete_sky_trial",
) -> dict:
    """Select first real matching entry of each typed RPG page in time order.

    The source timeline must come directly from the native RPG verifier.
    Replaying with the final manifest is mandatory; this helper alone is NOT
    a trustworthy approval and never mutates any gameplay state.
    """
    if (timeline.get("schema")!="skeleton.game.native_rpg_event_timeline.v1"
        or timeline.get("actor_id")!=actor_id or timeline.get("track")!=track
        or timeline.get("signed_gdd_digest")!=gdd_digest or
        timeline.get("authored_pages_digest")!=pages_digest or
        timeline.get("start_frame")!=0 or not timeline.get("entries")
        or timeline.get("receipt_digest")!=_digest({
            key:value for key,value in timeline.items() if key!="receipt_digest"
        })):
        raise ValueError("real source-verified RPG event prefix required")
    matched={}
    for entry in timeline["entries"]:
        if (entry["source_actor_id"]!=actor_id or entry["signed_gdd_digest"]!=gdd_digest
            or entry.get("receipt_digest")!=_digest({
                k:v for k,v in entry.items() if k!="receipt_digest"
            })):
            raise ValueError("foreign native actor/source event evidence")
        for proposal in entry["accepted_proposals"]:
            page=proposal["page_id"]
            if page==begin_page and page not in matched:
                matched[page]=(entry,proposal)
            if (page==complete_page and begin_page in matched
                and page not in matched
                and entry["frame"]>matched[begin_page][0]["frame"]):
                matched[page]=(entry,proposal)
    if set(matched)!={begin_page,complete_page}:
        raise ValueError("actual Godot start and later finish quest events required")
    approval_rows=[]
    for page in (begin_page,complete_page):
        event,proposal=matched[page]
        approval_rows.append({
            "frame":event["frame"],"page_id":page,
            "event_evidence_digest":proposal["event_evidence_digest"],
            "frame_receipt_digest":event["frame_receipt_digest"],
        })
    result={
        "schema":"skeleton.game.native_quest_approvals.v1",
        "session_id":"ci_godot_reference_quest_fixture",
        "actor_id":actor_id,"track":track,
        "signed_gdd_digest":gdd_digest,
        "authored_pages_digest":pages_digest,
        "quest_graph_digest":graph_digest,
        "initial_flags":{},"approvals":approval_rows,
    }
    result["receipt_digest"]=_digest(result)
    return result


def main(argv:list[str] | None = None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--signed-gdd",type=Path,required=True)
    parser.add_argument("--scene-json",type=Path,required=True)
    parser.add_argument("--journal",type=Path,required=True)
    parser.add_argument("--event-pages-json",type=Path,required=True)
    parser.add_argument("--quest-graph-json",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--actor-id",default="hero")
    args=parser.parse_args(argv)
    try:
        signed=bind_signed_gdd(_operator_json(args.signed_gdd))
        scene=_operator_json(args.scene_json)
        capture=scene.get("native_capture")
        if (scene.get("schema")!="skeleton.game.frontier_godot_overlay.v1" or
            not isinstance(capture,dict) or capture.get("enabled") is not True
            or capture.get("gdd_digest")!=signed.source_digest or
            capture.get("candidate_digest")!=scene.get("origin_candidate_digest")
            or capture.get("actor_id")!=args.actor_id):
            raise ValueError("signed scene and source actor identity required")
        raw_pages=_operator_json(args.event_pages_json)
        pages=parse_native_rpg_pages(raw_pages)
        graph=parse_native_quest_graph(_operator_json(args.quest_graph_json))
        with FrameReceiptJournal(args.journal,signed) as journal:
            # CI fixture learns where Godot actually moved and left the zone.
            # The complete prefix and event receipts are verified by the
            # canonical journal and existing read-only RPG page evaluator.
            timeline=evaluate_native_rpg_timeline(
                journal,pages,actor_id=args.actor_id,limit=4096,
                flags={"quest_active":True})
            approval=select_fixture_approvals(
                timeline,actor_id=args.actor_id,track=journal.track,
                gdd_digest=signed.source_digest,
                pages_digest=authored_page_digest(pages),
                graph_digest=graph["receipt_digest"])
            evidence=simulate_native_quest_session(
                journal,pages,graph,approval,actor_id=args.actor_id,
                scene_candidate_digest=capture["candidate_digest"],
                limit=4096)
            if (evidence["approved_page_count"]!=2 or
                evidence["final_quests"].get("sky_trial",{}).get("stage")!="finished" or
                evidence["final_quests"]["sky_trial"]["completed"] is not True or
                evidence["final_flags"].get("quest_active") is not True):
                raise ValueError("observed Godot quest did not complete against approved evidence")
        if (not args.output.parent.is_dir() or args.output.parent.is_symlink()
            or args.output.exists() or args.output.is_symlink()):
            raise ValueError("output approval path must be new and inside an existing folder")
        with args.output.open("x",encoding="utf-8") as source:
            json.dump(approval,source,sort_keys=True)
            source.write("\n")
        print(json.dumps({
            "schema":"skeleton.game.native_quest_ci_fixture_report.v1",
            "authority":"test_fixture_auto_selection_only_not_operator_authorization",
            "frames_verified":evidence["source_prefix_verified_frames"],
            "approved_event_frames":[x["frame"] for x in approval["approvals"]],
            "approval_digest":approval["receipt_digest"],
            "final_quest_stage":evidence["final_quests"]["sky_trial"]["stage"],
            "completed":True,
            "session_replay_digest":evidence["receipt_digest"],
        },sort_keys=True))
        return 0
    except (ValueError,OSError,KeyError,IndexError,TypeError) as exc:
        print(f"native Godot quest fixture failed closed: {exc}",file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
