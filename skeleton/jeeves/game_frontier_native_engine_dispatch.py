"""Source-verified local Godot quest dispatcher: verified actions, not AI scripts.

An explicitly approved native quest checkpoint is cold replayed from the
signed GDD, exact actor/source catalog and immutable Godot physics journal.
The resulting fixed-schema dispatch bundle is DATA, not executable GDScript.
Its approval is a local operator selection; the digest is integrity, not a
signature or network attestation. World canon remains unchanged.
"""
from __future__ import annotations

from hashlib import sha256
import json
from typing import Mapping

from .game_frontier_native_quest_session import (
    NativeQuestSessionError,_sha,parse_native_quest_graph,authored_page_digest,
)
from .game_frontier_native_quest_audit import audit_native_quest_checkpoint
from .game_frontier_native_session_checkpoint import advance_native_quest_window


_ALLOWED=frozenset((
    "start_quest","advance_quest","set_flag","show_dialogue",
    "play_cutscene","play_music","spatial_audio","change_camera",
    "inspect_instrument","trigger_impact_fx","trigger_foliage_fx",
))


def compile_native_godot_dispatch(
    journal,pages,quest_graph,approvals,checkpoint, *, actor_id: str,
    scene_candidate_digest: str, max_frames: int = 4096,
) -> dict:
    """Cold-audit a checkpoint; materialize only verified approved actions.

    The payload can be installed by an operator into an existing Godot
    scene; Godot validates the file digest against its source scene and
    applies the actions in order with an on-disk game-state receipt.
    """
    if type(max_frames) is not int or not 1<=max_frames<=4096:
        raise NativeQuestSessionError("bounded Godot dispatch export required")
    proof=audit_native_quest_checkpoint(
        journal,pages,quest_graph,approvals,checkpoint,
        actor_id=actor_id,scene_candidate_digest=scene_candidate_digest)
    last=checkpoint["frame"]
    if last+1>max_frames:
        raise NativeQuestSessionError(
            "interactive dispatch snapshot exceeds explicit frame limit")
    catalog=parse_native_quest_graph(quest_graph)
    commands=[]
    cursor=None
    for first in range(0,last+1,256):
        stop=min(last,first+255)
        response=advance_native_quest_window(
            journal,pages,quest_graph,approvals,
            actor_id=actor_id,scene_candidate_digest=scene_candidate_digest,
            through_frame=stop,previous_checkpoint=cursor,
            expected_checkpoint_digest=(
                cursor["receipt_digest"] if cursor is not None else None),
            max_frames=256)
        for entry in response["entries"]:
            for approved in entry["approved_pages"]:
                for index,action in enumerate(approved["actions"]):
                    if action["kind"] not in _ALLOWED:
                        raise NativeQuestSessionError(
                            "Godot dispatcher refuses unimplemented world mutations")
                    commands.append({
                        "frame":entry["frame"],
                        "page_id":approved["page_id"],
                        "action_index":index,
                        "kind":action["kind"],
                        "target":action["target"],
                        "value":action["value"],
                        "channel":action["channel"],
                        "native_frame_receipt_digest":entry["source_frame_receipt_digest"],
                        "approved_event_evidence_digest":approved["event_evidence_digest"],
                    })
        cursor=response["checkpoint"]
    if cursor!=checkpoint or len(commands)>65536:
        raise NativeQuestSessionError("dispatch actions differ from audited source prefix")
    result={
        "schema":"skeleton.game.native_godot_dispatch.v1",
        "source":"operator_approved_native_quest_source_replay",
        "authority":"local_gameplay_state_only_not_canonical_GDD_or_network_attestation",
        "actor_id":actor_id,
        "track":journal.track,
        "signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "authored_pages_digest":authored_page_digest(pages),
        "quest_graph_digest":catalog["receipt_digest"],
        "approved_manifest_digest":approvals["receipt_digest"],
        "verified_checkpoint_digest":checkpoint["receipt_digest"],
        "independent_cold_audit_digest":proof["receipt_digest"],
        "source_through_frame":last,
        "quest_start_stages":{item["id"]:item["start"]
                              for item in catalog["quests"]},
        "quest_edges":{item["id"]:{
            stage["id"]:stage["next"] for stage in item["stages"]}
            for item in catalog["quests"]},
        "initial_flags":dict(approvals["initial_flags"]),
        "expected_flags":checkpoint["flags"],
        "expected_quests":checkpoint["quests"],
        "actions":commands,
    }
    result["receipt_digest"]=_sha(result)
    return result


def verify_native_godot_dispatch(
    journal,pages,quest_graph,approvals,checkpoint,recorded: object,**kwargs
) -> bool:
    rebuilt=compile_native_godot_dispatch(
        journal,pages,quest_graph,approvals,checkpoint,**kwargs)
    if type(recorded) is not dict or recorded!=rebuilt:
        raise NativeQuestSessionError("in-engine dispatch bundle differs from verified journal")
    return True


def canonical_dispatch_json(dispatch: dict) -> str:
    """Exact byte stream for Godot FileAccess.get_sha256() comparison."""
    if (type(dispatch) is not dict or
        dispatch.get("schema")!="skeleton.game.native_godot_dispatch.v1"
        or dispatch.get("receipt_digest")!=_sha({
            k:v for k,v in dispatch.items() if k!="receipt_digest"})):
        raise NativeQuestSessionError("unverified dispatch bundle JSON")
    return json.dumps(dispatch,sort_keys=True,separators=(",",":"),
                      allow_nan=False)+"\n"


def dispatch_file_sha256(dispatch: dict) -> str:
    return sha256(canonical_dispatch_json(dispatch).encode("utf-8")).hexdigest()
