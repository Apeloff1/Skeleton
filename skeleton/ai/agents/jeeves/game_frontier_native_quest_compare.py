"""Compare independently replayed outcomes of one authored game quest timeline.

Two different approval selections may cause different branches and quest
results even against identical native physics. Both checkpoints must pass
a fresh full source replay; no client assertions or stale hashes are trusted.
"""
from __future__ import annotations

from .game_frontier_native_quest_session import (
    NativeQuestSessionError,_sha,parse_native_quest_graph,
)
from .game_frontier_native_quest_audit import audit_native_quest_checkpoint


def compare_native_quest_outcomes(
    left_journal,right_journal,pages,quest_graph,
    left_approvals,right_approvals,
    left_checkpoint,right_checkpoint, *, actor_id: str,
    scene_candidate_digest: str,
) -> dict:
    """Report factual diverging branches and flags, not an AI quality score."""
    if (type(left_checkpoint) is not dict or type(right_checkpoint) is not dict
        or left_checkpoint.get("frame")!=right_checkpoint.get("frame")):
        raise NativeQuestSessionError("quest outcomes require same fixed-tick source frame")
    graph=parse_native_quest_graph(quest_graph)
    left=audit_native_quest_checkpoint(
        left_journal,pages,quest_graph,left_approvals,left_checkpoint,
        actor_id=actor_id,scene_candidate_digest=scene_candidate_digest)
    right=audit_native_quest_checkpoint(
        right_journal,pages,quest_graph,right_approvals,right_checkpoint,
        actor_id=actor_id,scene_candidate_digest=scene_candidate_digest)
    if (left["signed_gdd_digest"]!=right["signed_gdd_digest"]
        or left["authored_pages_digest"]!=right["authored_pages_digest"]
        or left["quest_graph_digest"]!=right["quest_graph_digest"]):
        raise NativeQuestSessionError("cross-session game canon, pages or authored quests differ")
    from copy import deepcopy
    def differences(field):
        a=left_checkpoint[field]
        b=right_checkpoint[field]
        return [{
            "id":key,
            "left":deepcopy(a.get(key)),
            "right":deepcopy(b.get(key)),
            "left_present":key in a,"right_present":key in b,
        } for key in sorted(set(a)|set(b)) if (
            key not in a or key not in b or a[key]!=b[key])]
    left_rows={(row["frame"],row["page_id"]) for row in left_checkpoint["approved_rows"]}
    right_rows={(row["frame"],row["page_id"]) for row in right_checkpoint["approved_rows"]}
    report={
        "schema":"skeleton.game.native_quest_branch_comparison.v1",
        "signed_gdd_digest":left["signed_gdd_digest"],
        "authored_quest_graph_digest":graph["receipt_digest"],
        "scene_candidate_digest":scene_candidate_digest,
        "actor_id":actor_id,
        "compared_frame":left_checkpoint["frame"],
        "left_track":left_journal.track,
        "right_track":right_journal.track,
        "left_checkpoint_digest":left_checkpoint["receipt_digest"],
        "right_checkpoint_digest":right_checkpoint["receipt_digest"],
        "left_audit_digest":left["receipt_digest"],
        "right_audit_digest":right["receipt_digest"],
        "changed_quests":differences("quests"),
        "changed_flags":differences("flags"),
        "approved_only_on_left":[{"frame":k[0],"page_id":k[1]}
                                 for k in sorted(left_rows-right_rows)],
        "approved_only_on_right":[{"frame":k[0],"page_id":k[1]}
                                  for k in sorted(right_rows-left_rows)],
        "native_frame_digest_equal":(
            left_checkpoint["frame_receipt_digest"]==
            right_checkpoint["frame_receipt_digest"]),
        "identical_quest_state":(
            left_checkpoint["quests"]==right_checkpoint["quests"]
            and left_checkpoint["flags"]==right_checkpoint["flags"]),
        "authority":"independently_audited_alternative_RPG_sessions_not_canon_merge",
    }
    report["receipt_digest"]=_sha(report)
    return report
