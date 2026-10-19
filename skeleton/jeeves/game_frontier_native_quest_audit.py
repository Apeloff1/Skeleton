"""Independent cold-replay audit of retained quest continuation checkpoints.

Unlike trusting a SHA passed along with the same file, this audits every
game physics tick from frame zero and recomputes RPG decisions, flags, quests,
cooldowns and approval history from canonical data. This costs O(history);
use at admission/restore checkpoints, not on every physics tick.
"""
from __future__ import annotations

from .game_frontier_native_quest_session import NativeQuestSessionError,_sha
from .game_frontier_native_quest_batch import replay_native_quest_batches


def audit_native_quest_checkpoint(
    journal,pages,quest_graph,approval,checkpoint, *,
    actor_id: str,scene_candidate_digest: str,
    frames_per_window: int = 256,
) -> dict:
    """Cold-replay entire signed/GDD-bound prefix, comparing exact cursor state."""
    if (type(checkpoint) is not dict or
        checkpoint.get("schema")!="skeleton.game.native_quest_resume_checkpoint.v1" or
        type(checkpoint.get("frame")) is not int or checkpoint["frame"]<0):
        raise NativeQuestSessionError("auditable native game checkpoint required")
    verified=replay_native_quest_batches(
        journal,pages,quest_graph,approval,actor_id=actor_id,
        scene_candidate_digest=scene_candidate_digest,
        through_frame=checkpoint["frame"],
        frames_per_window=frames_per_window)
    calculated=verified["head_checkpoint"]
    if calculated!=checkpoint:
        raise NativeQuestSessionError(
            "quest checkpoint differs from independent full source-history replay")
    report={
        "schema":"skeleton.game.native_quest_checkpoint_audit.v1",
        "track":journal.track,"actor_id":actor_id,
        "signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "checkpoint_frame":checkpoint["frame"],
        "checkpoint_digest":checkpoint["receipt_digest"],
        "native_journal_frame_digest":checkpoint["frame_receipt_digest"],
        "verified_source_prefix_frames":verified["verified_frame_count"],
        "batch_chain_head_digest":verified["batch_chain_head_digest"],
        "authored_pages_digest":verified["authored_pages_digest"],
        "quest_graph_digest":verified["quest_graph_digest"],
        "approved_events_verified":verified["total_approved_events"],
        "source_replay_consistent":True,
        "authority":"verified_source_history_not_authorization_or_canon_write",
    }
    report["receipt_digest"]=_sha(report)
    return report


def verify_native_quest_checkpoint_audit(
    journal,pages,quest_graph,approval,checkpoint,recorded: object,**kwargs
) -> bool:
    """Refuse a modified audit or checkpoint receipt, even when it rehashes."""
    fresh=audit_native_quest_checkpoint(
        journal,pages,quest_graph,approval,checkpoint,**kwargs)
    if type(recorded) is not dict or fresh!=recorded:
        raise NativeQuestSessionError("checkpoint audit evidence disagrees with source")
    return True
