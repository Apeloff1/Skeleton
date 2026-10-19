"""Bounded, resumable native RPG quest sessions anchored to Godot receipt journal.

A checkpoint is a content-hashed continuation token, NOT an authentication
signature. A trusted caller must retain the earlier validated checkpoint;
untrusted clients cannot gain approval merely by submitting a matching hash.
The operator manifest binds all approved events to the original frame digest.
The immutable native journal is checked before every continuation.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Mapping

from skeleton.forge.game_frontier_rpg_events import (
    RPGEventPage,evaluate_environment_events,
)
from .game_frontier_native_rpg_bridge import native_rpg_observations,NATIVE_RPG_SIGNALS
from .game_frontier_native_quest_session import (
    NativeQuestSessionError, _approved_manifest, _stage_snapshot, _apply_page,
    _sha, _HEX, _ID, authored_page_digest, parse_native_quest_graph,
)
from .game_frontier_receipt_journal import FrameReceiptJournal


_CURSOR_SCHEMA="skeleton.game.native_quest_resume_checkpoint.v1"
_WINDOW_SCHEMA="skeleton.game.native_quest_session_window.v1"


def _require_checkpoint(checkpoint: object, *, journal: FrameReceiptJournal,
                        source: str, actor: str, pages_hash: str,
                        graph: dict, approval: dict) -> dict:
    if not isinstance(checkpoint,dict) or set(checkpoint)!={
        "schema","session_id","track","actor_id","signed_gdd_digest",
        "scene_candidate_digest","authored_pages_digest","quest_graph_digest",
        "initial_flags_digest","frame","frame_receipt_digest",
        "native_source_digest","last_session_receipt_digest",
        "clock_ms","flags","quests","last_fired_ms",
        "completed_once_page_ids","previous_observations",
        "approved_rows","approved_page_count","receipt_digest",
    } or checkpoint.get("schema")!=_CURSOR_SCHEMA:
        raise NativeQuestSessionError("exact durable game session checkpoint required")
    root=checkpoint["receipt_digest"]
    if (type(root) is not str or _HEX.fullmatch(root) is None
        or root!=_sha({k:v for k,v in checkpoint.items() if k!="receipt_digest"})
        or checkpoint["session_id"]!=approval["session_id"]
        or checkpoint["track"]!=journal.track
        or checkpoint["actor_id"]!=actor
        or checkpoint["signed_gdd_digest"]!=journal.gdd.source_digest
        or checkpoint["scene_candidate_digest"]!=source
        or checkpoint["authored_pages_digest"]!=pages_hash
        or checkpoint["quest_graph_digest"]!=graph["receipt_digest"]
        or checkpoint["initial_flags_digest"]!=_sha(approval["initial_flags"])):
        raise NativeQuestSessionError("checkpoint corrupted or bound to another game source")
    i=checkpoint["frame"]
    if type(i) is not int or i<0 or i>journal.stats()["head"]:
        raise NativeQuestSessionError("checkpoint points outside retained journal")
    old_frame,_=journal.load(i)
    old_native=journal.native_sample(i)
    if (old_native is None
        or old_frame.receipt_digest!=checkpoint["frame_receipt_digest"]
        or _sha(old_native)!=checkpoint["native_source_digest"]
        or old_frame.time_ns//1_000_000!=checkpoint["clock_ms"]
        or old_native.get("scene_candidate_digest")!=source):
        raise NativeQuestSessionError("resume anchor differs from immutable native source")
    for key in ("frame_receipt_digest","native_source_digest",
                "last_session_receipt_digest"):
        x=checkpoint[key]
        if type(x) is not str or _HEX.fullmatch(x) is None:
            raise NativeQuestSessionError("invalid hashed checkpoint root")
    flags=checkpoint["flags"]
    fired=checkpoint["last_fired_ms"]
    observed=checkpoint["previous_observations"]
    once=checkpoint["completed_once_page_ids"]
    quests=checkpoint["quests"]
    rows=checkpoint["approved_rows"]
    count=checkpoint["approved_page_count"]
    if (type(flags) is not dict or len(flags)>4096 or
        any(type(k) is not str or _ID.fullmatch(k) is None or
            type(v) is not bool for k,v in flags.items()) or
        type(fired) is not dict or len(fired)>4096 or
        any(type(k) is not str or _ID.fullmatch(k) is None or
            type(v) is not int or not 0<=v<=checkpoint["clock_ms"]
            for k,v in fired.items()) or
        type(once) is not list or len(once)>4096 or
        len(set(once))!=len(once) or
        any(type(k) is not str or _ID.fullmatch(k) is None for k in once) or
        type(observed) is not dict or len(observed)>256 or
        any(k not in NATIVE_RPG_SIGNALS or type(v) not in (int,float)
            or not math.isfinite(v) for k,v in observed.items()) or
        type(quests) is not dict or len(quests)>128 or
        type(rows) is not list or len(rows)>100000 or
        type(count) is not int or count!=len(rows)):
        raise NativeQuestSessionError("malformed or out-of-bounds checkpoint state")
    graph_index=_stage_snapshot(graph)
    for name,progress in quests.items():
        if (name not in graph_index or type(progress) is not dict
            or set(progress)!={"stage","completed","last_transition_frame"}
            or progress["stage"] not in graph_index[name]["edges"]
            or type(progress["completed"]) is not bool
            or progress["completed"]!=(
                not bool(graph_index[name]["edges"][progress["stage"]]))
            or type(progress["last_transition_frame"]) is not int
            or not 0<=progress["last_transition_frame"]<=i):
            raise NativeQuestSessionError("checkpoint contradicts authored stage graph")
    native_observations=native_rpg_observations(old_native,actor_id=actor)
    if observed!=native_observations:
        raise NativeQuestSessionError("previous observed RPG physics was altered")
    if set(fired)!=set(once):
        raise NativeQuestSessionError("page cooldown and one-shot state diverged")
    if len(rows)!=len({(entry["frame"],entry["page_id"]) for entry in rows
                      if type(entry) is dict and "frame" in entry and
                      "page_id" in entry}):
        raise NativeQuestSessionError("duplicate approved event in game checkpoint")
    return checkpoint


def advance_native_quest_window(
    journal: FrameReceiptJournal, pages: tuple[RPGEventPage,...],
    quest_graph: object, approval: object, *,
    actor_id: str, scene_candidate_digest: str,
    through_frame: int | None = None,
    previous_checkpoint: dict | None = None,
    max_frames: int = 256,
) -> dict:
    """Consume a bounded contiguous native replay window and output next cursor.

    First window runs canonical full-prefix replay. A continuation verifies
    its trusted predecessor against CAS source, then independently checks
    only the next bounded native window. Approval entries for past frames
    are append-only. Unapproved page proposals still consume cooldown/once,
    but never modify the quest state or flags.
    """
    if (not isinstance(journal,FrameReceiptJournal)
        or type(actor_id) is not str or not 1<=len(actor_id)<=128
        or type(scene_candidate_digest) is not str
        or _HEX.fullmatch(scene_candidate_digest) is None
        or type(max_frames) is not int or not 1<=max_frames<=4096
        or through_frame is not None and (
            type(through_frame) is not int or through_frame<0)):
        raise NativeQuestSessionError("bounded native quest continuation required")
    graph=parse_native_quest_graph(quest_graph)
    pages_hash=authored_page_digest(pages)
    approved=_approved_manifest(approval,journal=journal,actor_id=actor_id,
                                page_hash=pages_hash,
                                quest_hash=graph["receipt_digest"])
    current_head=journal.stats()["head"]
    finish=current_head if through_frame is None else through_frame
    if previous_checkpoint is None:
        begin=0
        flags=dict(approval["initial_flags"])
        quests={}
        prior={}
        fired={}
        completed=set()
        previous_receipt=None
        consumed={}
        old_count=0
        old_frame_digest=None
    else:
        previous=_require_checkpoint(
            previous_checkpoint,journal=journal,source=scene_candidate_digest,
            actor=actor_id,pages_hash=pages_hash,graph=graph,approval=approval)
        begin=previous["frame"]+1
        flags=dict(previous["flags"])
        quests={key:dict(value) for key,value in previous["quests"].items()}
        prior=dict(previous["previous_observations"])
        fired=dict(previous["last_fired_ms"])
        completed=set(previous["completed_once_page_ids"])
        previous_receipt=previous["last_session_receipt_digest"]
        consumed={(row["frame"],row["page_id"]):row
                  for row in previous["approved_rows"]}
        old_count=previous["approved_page_count"]
        old_frame_digest=previous["frame_receipt_digest"]
        # A different approval at an already committed frame cannot rewrite
        # the past event decisions even if the JSON digest was recomputed.
        for key,row in consumed.items():
            if approved.get(key)!=row:
                raise NativeQuestSessionError("previously approved game event was rewritten")
        for key in approved:
            if key[0]<begin and key not in consumed:
                raise NativeQuestSessionError("past events cannot receive retroactive approval")
    if (begin>finish or finish>current_head or finish>1000000
        or finish-begin+1>max_frames):
        raise NativeQuestSessionError("new native RPG window is not contiguous and bounded")
    # New segment verifier uses source CAS + predecessor state to avoid
    # replaying all earlier frame chunks on every 256-frame continuation.
    source_replay=journal.verify_native_segment(
        start_frame=begin,through=finish,
        predecessor_frame_digest=old_frame_digest)
    if source_replay["verified_frames"]!=finish-begin+1:
        raise NativeQuestSessionError("source segment was not completely verified")
    definitions=_stage_snapshot(graph)
    entries=[]
    for i in range(begin,finish+1):
        native=journal.native_sample(i)
        if (native is None or native.get("scene_candidate_digest")!=scene_candidate_digest
            or native.get("signed_gdd_digest")!=journal.gdd.source_digest):
            raise NativeQuestSessionError("foreign source scene or signed GDD")
        frame,chunk=journal.load(i)
        current=native_rpg_observations(native,actor_id=actor_id)
        moment=frame.time_ns//1_000_000
        choice=evaluate_environment_events(
            pages,current=current,previous=prior,flags=flags,
            now_ms=moment,last_fired_ms=fired,
            completed_once=frozenset(completed))
        proposed=[]
        applied=[]
        cues=[]
        for event in choice.accepted:
            fired[event.page_id]=moment
            completed.add(event.page_id)
            key=(i,event.page_id)
            decision=approved.get(key)
            proposed.append({
                "page_id":event.page_id,
                "event_evidence_digest":event.evidence_digest,
                "operator_approved":decision is not None,
            })
            if decision is not None:
                if (decision["event_evidence_digest"]!=event.evidence_digest
                    or decision["frame_receipt_digest"]!=frame.receipt_digest):
                    raise NativeQuestSessionError("approved event evidence differs from Godot")
                actions=[action.__dict__ for action in event.actions]
                quests,flags,next_cues=_apply_page(
                    actions,actor_id=actor_id,graph=definitions,
                    quests=quests,flags=flags,frame=i)
                cues.extend(next_cues)
                consumed[key]=decision
                applied.append({"page_id":event.page_id,"actions":actions,
                                "event_evidence_digest":event.evidence_digest})
        entry={
            "frame":i,"clock_ns":frame.time_ns,
            "source_frame_receipt_digest":frame.receipt_digest,
            "source_chunk_digest":chunk["receipt_digest"],
            "source_native_digest":_sha(native),
            "previous_session_receipt_digest":previous_receipt,
            "proposals":proposed,"approved_pages":applied,
            "suppressed_page_ids":list(choice.suppressed),
            "missing_observations":list(choice.missing_signals),
            "quests":{k:quests[k] for k in sorted(quests)},
            "flags":{k:flags[k] for k in sorted(flags)},
            "presentation_cues":cues,
        }
        entry["receipt_digest"]=_sha(entry)
        entries.append(entry)
        previous_receipt=entry["receipt_digest"]
        prior=current
    for key in approved:
        if key[0]<=finish and key not in consumed:
            raise NativeQuestSessionError("selected approval did not match a real native event")
    last,chunk=journal.load(finish)
    assert last.receipt_digest==entries[-1]["source_frame_receipt_digest"]
    cursor={
        "schema":_CURSOR_SCHEMA,
        "session_id":approval["session_id"],"track":journal.track,
        "actor_id":actor_id,"signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "authored_pages_digest":pages_hash,
        "quest_graph_digest":graph["receipt_digest"],
        "initial_flags_digest":_sha(approval["initial_flags"]),
        "frame":finish,
        "frame_receipt_digest":last.receipt_digest,
        "native_source_digest":_sha(journal.native_sample(finish)),
        "last_session_receipt_digest":previous_receipt,
        "clock_ms":last.time_ns//1_000_000,
        "flags":{key:flags[key] for key in sorted(flags)},
        "quests":{key:quests[key] for key in sorted(quests)},
        "last_fired_ms":{key:fired[key] for key in sorted(fired)},
        "completed_once_page_ids":sorted(completed),
        "previous_observations":prior,
        "approved_rows":[consumed[key] for key in sorted(consumed)],
        "approved_page_count":len(consumed),
    }
    cursor["receipt_digest"]=_sha(cursor)
    report={
        "schema":_WINDOW_SCHEMA,
        "session_id":approval["session_id"],
        "actor_id":actor_id,
        "track":journal.track,"signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "start_frame":begin,"through_frame":finish,
        "verified_window_frames":len(entries),
        "previous_checkpoint_digest":(
            previous_checkpoint["receipt_digest"]
            if previous_checkpoint is not None else None),
        "approved_page_count_delta":len(consumed)-old_count,
        "approved_page_count_total":len(consumed),
        "entries":entries,
        "checkpoint":cursor,
        "authority":"source_verified_local_quest_session_not_engine_world_save",
    }
    report["receipt_digest"]=_sha(report)
    return report


def verify_native_quest_window(
    journal: FrameReceiptJournal, pages: tuple[RPGEventPage,...],
    quest_graph: object, approval: object, recorded: dict, **kwargs
) -> bool:
    """Recompute a window from trusted checkpoint and immutable Godot source."""
    rebuilt=advance_native_quest_window(journal,pages,quest_graph,approval,**kwargs)
    if type(recorded) is not dict or rebuilt!=recorded:
        raise NativeQuestSessionError("quest continuation differs from source replay")
    return True
