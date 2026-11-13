"""Long-running native game quest replay, one bounded verified window at a time.

Keeps one checkpoint in memory, with an independently chained per-window
progress receipt. Consumes all retained journal frames without silently
resetting one-shot triggers, flags, quest branches or approved event history.
Not a model-training loop or proof of long-duration hardware reliability.
"""
from __future__ import annotations
from hashlib import sha256
import json
from typing import Mapping

from .game_frontier_receipt_journal import FrameReceiptJournal
from .game_frontier_native_quest_session import (
    NativeQuestSessionError,authored_page_digest,parse_native_quest_graph,_sha,
)
from .game_frontier_native_session_checkpoint import advance_native_quest_window


def replay_native_quest_batches(
    journal: FrameReceiptJournal, pages: tuple, quest_graph: object,
    approval: object, *, actor_id: str, scene_candidate_digest: str,
    through_frame: int | None = None, frames_per_window: int = 256,
    resume_checkpoint: Mapping | None = None,
    expected_checkpoint_digest: str | None = None,
) -> dict:
    """Replay full recorded source or resume from a separately trusted cursor.

    Individual windows stay within the typed fixed-tick verifier's memory and
    temporal budget. Only progress summaries, not all frame entries, are
    retained in this aggregate. The caller owns durable save/restore policy.
    """
    if (not isinstance(journal,FrameReceiptJournal)
        or type(frames_per_window) is not int
        or not 1<=frames_per_window<=4096):
        raise NativeQuestSessionError("bounded native quest batch request required")
    head=journal.stats()["head"]
    last=head if through_frame is None else through_frame
    if type(last) is not int or last<0 or last>head:
        raise NativeQuestSessionError("quest batch end outside source journal")
    cursor=resume_checkpoint
    if cursor is None and expected_checkpoint_digest is not None:
        raise NativeQuestSessionError("unexpected trusted checkpoint root")
    if cursor is not None and (
        type(cursor) is not dict or type(cursor.get("frame")) is not int
        or cursor["frame"]>=last):
        raise NativeQuestSessionError("resume must advance after a completed frame")
    previous_window=None
    verified=0
    delta_approvals=0
    windows=[]
    starting_frame=0 if cursor is None else cursor["frame"]+1
    next_frame=starting_frame
    while next_frame<=last:
        end=min(last,next_frame+frames_per_window-1)
        window=advance_native_quest_window(
            journal,pages,quest_graph,approval,actor_id=actor_id,
            scene_candidate_digest=scene_candidate_digest,
            through_frame=end,previous_checkpoint=cursor,
            expected_checkpoint_digest=expected_checkpoint_digest,
            max_frames=frames_per_window)
        if (window["start_frame"]!=next_frame or
            window["through_frame"]!=end or
            window["verified_window_frames"]!=end-next_frame+1 or
            (cursor is not None and
             window["previous_checkpoint_digest"]!=cursor["receipt_digest"])):
            raise NativeQuestSessionError("noncontiguous native quest batch proof")
        previous_receipt=window["receipt_digest"]
        checkpoint=window["checkpoint"]
        item={
            "start_frame":next_frame,"through_frame":end,
            "verified_frames":window["verified_window_frames"],
            "approved_pages":window["approved_page_count_delta"],
            "previous_batch_receipt_digest":previous_window,
            "window_receipt_digest":previous_receipt,
            "checkpoint_digest":checkpoint["receipt_digest"],
            "session_receipt_digest":checkpoint["last_session_receipt_digest"],
        }
        item["receipt_digest"]=_sha(item)
        windows.append(item)
        previous_window=item["receipt_digest"]
        verified+=item["verified_frames"]
        delta_approvals+=item["approved_pages"]
        cursor=checkpoint
        expected_checkpoint_digest=cursor["receipt_digest"]
        next_frame=end+1
    if (cursor is None or verified!=last-starting_frame+1
        or sum(x["approved_pages"] for x in windows)!=delta_approvals):
        raise NativeQuestSessionError("incomplete native quest batch coverage")
    report={
        "schema":"skeleton.game.native_quest_batch_replay.v1",
        "actor_id":actor_id,"track":journal.track,
        "signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "authored_pages_digest":authored_page_digest(pages),
        "quest_graph_digest":parse_native_quest_graph(quest_graph)["receipt_digest"],
        "start_frame":starting_frame,"through_frame":last,
        "verified_frame_count":verified,
        "window_count":len(windows),
        "newly_approved_events":delta_approvals,
        "total_approved_events":cursor["approved_page_count"],
        "window_evidence":windows,
        "head_checkpoint":cursor,
        "batch_chain_head_digest":previous_window,
        "authority":"verified_local_quest_batches_not_canonical_world_save",
    }
    report["receipt_digest"]=_sha(report)
    return report


def verify_native_quest_batch_report(
    journal: FrameReceiptJournal,pages: tuple,quest_graph: object,
    approval: object,report: dict,**kwargs
) -> bool:
    """Reconstruct every batch and detect summary, cursor or chain tampering."""
    original=replay_native_quest_batches(
        journal,pages,quest_graph,approval,**kwargs)
    if type(report) is not dict or original!=report:
        raise NativeQuestSessionError("recorded quest batch differs from source replay")
    return True
