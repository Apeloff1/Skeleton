"""Verified read-only native checkpoint-branch difference report.

Compare the native action/frame/audio sequence following a private checkpoint
with one subsequent rewind branch. Uses only hash-bound session receipts:
no savestate bytes, pixels, PCM, source ROM, reward inference or model updates.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .game_comparison_live_evidence import verify_live_evidence
from .game_comparison_schema import digest

SCHEMA="skeleton.game.live_branch_difference.v1"


def build_live_branch_difference_report(packet:Mapping[str,Any])->dict[str,Any]:
    checked=verify_live_evidence(packet)
    entries=[]
    for game in checked["games"]:
        gid=game["game_id"]
        original=packet["lanes"][gid]["native_events"]
        comparisons=[]
        for index,event in enumerate(original):
            if event["event_kind"]!="native_rewind":
                continue
            receipt=event["receipt"]
            checkpoint_id=receipt["checkpoint_id"]
            before_checkpoint=next((
                offset for offset in range(index-1,-1,-1)
                if original[offset]["event_kind"]=="native_checkpoint"
                and original[offset]["receipt"]["checkpoint_id"]==checkpoint_id
            ),None)
            if before_checkpoint is None:
                raise ValueError("Verified rewind lost its checkpoint linkage")
            # The original path ends at this rewind. A reset or another
            # rewind ends the alternative path. Metadata-only checkpoints
            # do not count as controller actions.
            prior_branch_boundary=max(
                (
                    offset for offset in range(before_checkpoint+1,index)
                    if original[offset]["event_kind"] in ("native_rewind","native_reset")
                ),
                default=before_checkpoint,
            )
            baseline=[
                row["receipt"] for row in original[prior_branch_boundary+1:index]
                if row["event_kind"]=="native_step"
            ]
            alternate=[]
            for row in original[index+1:]:
                if row["event_kind"] in ("native_reset","native_rewind"):
                    break
                if row["event_kind"]=="native_step":
                    alternate.append(row["receipt"])
            common=min(len(baseline),len(alternate))
            actions=[
                offset+1 for offset in range(common)
                if baseline[offset]["input_vector_sha256"]!=alternate[offset]["input_vector_sha256"]
            ]
            frames=[
                offset+1 for offset in range(common)
                if baseline[offset]["frame_sha256"]!=alternate[offset]["frame_sha256"]
            ]
            pcm=[
                offset+1 for offset in range(common)
                if baseline[offset]["pcm_sha256"]!=alternate[offset]["pcm_sha256"]
            ]
            comparisons.append({
                "checkpoint_id":checkpoint_id,
                "rewind_generation":receipt["rewind_generation"],
                "original_episode_step":receipt["restored_episode_step"],
                "original_path_native_steps":len(baseline),
                "rewound_path_native_steps":len(alternate),
                "aligned_input_steps":common,
                "different_controller_step_offsets":actions,
                "different_native_frame_step_offsets":frames,
                "different_native_pcm_step_offsets":pcm,
                "first_controller_difference_offset":actions[0] if actions else None,
                "first_video_difference_offset":frames[0] if frames else None,
                "first_audio_difference_offset":pcm[0] if pcm else None,
                "original_branch_last_receipt_sha256":(
                    baseline[-1]["receipt_sha256"] if baseline else None
                ),
                "rewound_branch_last_receipt_sha256":(
                    alternate[-1]["receipt_sha256"] if alternate else None
                ),
                "matching_controller_input_proves_identical_gameplay":False,
                "change_in_game_mechanics_or_training_proven":False,
                "within_branch_independent_repeatability_proven":False,
            })
        entries.append({
            "game_id":gid,
            "verified_checkpoint_count":game["native_checkpoints_verified"],
            "verified_rewind_count":game["native_rewinds_verified"],
            "branch_comparisons":comparisons,
            "fresh_reset_replay_gate":game["replay_gate"],
        })
    report={
        "schema_version":SCHEMA,
        "source_study_id":packet["study_id"],
        "source_live_verification_sha256":checked["verification_sha256"],
        "game_count":len(entries),
        "games":entries,
        "only_sha_linked_native_observations_included":True,
        "native_snapshot_game_memory_or_pcm_exported":False,
        "casual_causal_interpretation_disallowed":True,
        "independent_fresh_worker_replay_completed":False,
        "production_llm_weights_changed":False,
    }
    report["branch_report_sha256"]=digest(report)
    return report
