"""Read-only player quest journal from cold-audited native game progression.

Objective, next branches, and fictional game-map position derive from the
authored quest graph and a real Godot frame, never speculative AI dialogue.
It is an inspector payload for Studio/game UI, not an executor.
"""
from __future__ import annotations

from .game_frontier_native_quest_session import (
    NativeQuestSessionError,parse_native_quest_graph,_sha,
)
from .game_frontier_native_quest_audit import verify_native_quest_checkpoint_audit


def inspect_native_quest_objectives(
    journal,pages,quest_graph,approvals,checkpoint,audit_receipt, *,
    actor_id: str,scene_candidate_digest: str,
) -> dict:
    """Return complete quest-state and next decision affordances with evidence."""
    verify_native_quest_checkpoint_audit(
        journal,pages,quest_graph,approvals,checkpoint,audit_receipt,
        actor_id=actor_id,scene_candidate_digest=scene_candidate_digest)
    graph=parse_native_quest_graph(quest_graph)
    stage_lookup={}
    status=[]
    for quest in graph["quests"]:
        nodes={stage["id"]:stage for stage in quest["stages"]}
        stage_lookup[quest["id"]]=nodes
        state=checkpoint["quests"].get(quest["id"])
        if state is None:
            status.append({
                "quest_id":quest["id"],"title":quest["title"],
                "status":"not_started","stage_id":None,
                "current_objective":None,"next_options":[],
                "last_transition_frame":None,
                "source_graph_digest":graph["receipt_digest"],
            })
            continue
        stage=nodes.get(state.get("stage"))
        if stage is None:
            raise NativeQuestSessionError("quest checkpoint stage not authored")
        completed=not stage["next"]
        if completed!=state["completed"]:
            raise NativeQuestSessionError("quest completed flag contradicts authored branch")
        status.append({
            "quest_id":quest["id"],"title":quest["title"],
            "status":"completed" if completed else "in_progress",
            "stage_id":stage["id"],"current_objective":stage["objective"],
            "next_options":[{
                "stage_id":sid,
                "objective":nodes[sid]["objective"]
            } for sid in stage["next"]],
            "last_transition_frame":state["last_transition_frame"],
            "source_graph_digest":graph["receipt_digest"],
        })
    frame=checkpoint["frame"]
    sample=journal.native_sample(frame)
    if (sample is None or sample.get("scene_candidate_digest")!=scene_candidate_digest):
        raise NativeQuestSessionError("quest location source no longer matches scene")
    found=[actor for actor in sample["actors"] if actor["id"]==actor_id]
    if len(found)!=1:
        raise NativeQuestSessionError("quest journal actor must resolve in real physics source")
    world_xyz=found[0]["world_xyz_m"]
    velocity=found[0]["velocity_xyz_mps"]
    report={
        "schema":"skeleton.game.native_quest_objective_journal.v1",
        "actor_id":actor_id,"track":journal.track,
        "signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "source_frame":frame,
        "source_frame_receipt_digest":checkpoint["frame_receipt_digest"],
        "source_checkpoint_digest":checkpoint["receipt_digest"],
        "checkpoint_audit_digest":audit_receipt["receipt_digest"],
        "authored_quest_graph_digest":graph["receipt_digest"],
        "quest_total":len(status),
        "quests_not_started":sum(q["status"]=="not_started" for q in status),
        "quests_active":sum(q["status"]=="in_progress" for q in status),
        "quests_completed":sum(q["status"]=="completed" for q in status),
        "quest_entries":status,
        "game_only_virtual_position_xyz_m":world_xyz,
        "game_only_velocity_xyz_mps":velocity,
        "approved_event_count":checkpoint["approved_page_count"],
        "read_only_flags":dict(sorted(checkpoint["flags"].items())),
        "authority":"read_only_audited_game_state_not_real_GPS_or_canon_writer",
    }
    report["receipt_digest"]=_sha(report)
    return report
