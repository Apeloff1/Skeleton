"""Repeatable save/restart/fault-injection qualification for long game sessions.

This measures *actual* bounded SQLite close/reopen and source-replay cycles
against a user-selected native Godot journal. It cannot honestly certify a
month or year of uptime without such a test; it supplies the durable loop,
observability and fail-closed checkpoints to support extended production.
"""
from __future__ import annotations
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import time

from .game_frontier_native_quest_session import NativeQuestSessionError,_sha
from .game_frontier_native_quest_batch import replay_native_quest_batches
from .game_frontier_native_session_vault import NativeSessionVault,NativeSessionVaultError


def exercise_native_session_endurance(
    journal,pages,quest_graph,approvals,*,actor_id:str,
    scene_candidate_digest:str,vault_path:Path,
    cycles:int=12,window_frames:int=32,retain_latest:int=2,
    crash_interval:int=5,
    max_cycle_ms:int | None = None,
    max_vault_bytes:int | None = None,
) -> dict:
    """Close/open save vault every cycle, cold audit source and inject rollbacks.

    Not a wall-clock stress test: caller controls cadence/iterations, source
    journal is read-only and canonical GDD is never updated. No fake completion
    percentages, GPU measurements, or source-validation bypasses.
    """
    if (type(cycles) is not int or not 1<=cycles<=1024
        or type(window_frames) is not int or not 1<=window_frames<=4096
        or type(retain_latest) is not int or not 1<=retain_latest<=1024
        or type(crash_interval) is not int or not 0<=crash_interval<=1024
        or not isinstance(vault_path,Path)
        or (max_cycle_ms is not None and (type(max_cycle_ms) is not int or not 1<=max_cycle_ms<=3_600_000))
        or (max_vault_bytes is not None and (type(max_vault_bytes) is not int or not 1<=max_vault_bytes<=1_000_000_000_000))):
        raise NativeSessionVaultError("bounded endurance profile required")
    stats=journal.stats()
    head=stats["head"]
    if head<0:
        raise NativeSessionVaultError("real source frames required for endurance")
    last_frame=-1
    saved_root=None
    first=time.monotonic_ns()
    failures_injected=0
    successful_restarts=0
    duplicate_saves=0
    committed_saves=0
    journal_rows=[]
    session_id=approvals["session_id"]
    for cycle in range(cycles):
        cycle_start_ns=time.monotonic_ns()
        # Interleave actual new verified game frames (where available) with
        # restart-only cycles to exercise idempotent recovery.
        target=min(head,((cycle+1)*(head+1)+cycles-1)//cycles-1)
        target=max(0,target)
        if target<last_frame:
            raise NativeSessionVaultError("endurance source target regressed")
        batch=replay_native_quest_batches(
            journal,pages,quest_graph,approvals,actor_id=actor_id,
            scene_candidate_digest=scene_candidate_digest,
            through_frame=target,frames_per_window=window_frames)
        if batch["head_checkpoint"]["frame"]!=target:
            raise NativeSessionVaultError("source prefix replay did not reach game head")
        with NativeSessionVault(vault_path,session_id=session_id) as writer:
            if crash_interval and (cycle+1)%crash_interval==0 and target>last_frame:
                try:
                    writer.append(batch["head_checkpoint"],journal,pages,
                        quest_graph,approvals,actor_id=actor_id,
                        scene_candidate_digest=scene_candidate_digest,
                        inject_crash_before_commit=True)
                except NativeSessionVaultError as exc:
                    if "injected write interruption" not in str(exc):
                        raise
                    failures_injected+=1
                else:
                    raise NativeSessionVaultError("injected write failed to interrupt")
            commit=writer.append(batch["head_checkpoint"],journal,pages,
                                 quest_graph,approvals,actor_id=actor_id,
                                 scene_candidate_digest=scene_candidate_digest)
            committed_saves+=int(not commit["reused_existing"])
            duplicate_saves+=int(commit["reused_existing"])
            rotate=writer.rotate(keep_latest=retain_latest)
            saved_root=rotate["head_receipt_digest"]
        # Reopen from scratch after closing the SQLite connection and
        # independently reauthenticate the latest source against GDD.
        with NativeSessionVault(vault_path,session_id=session_id) as reader:
            resumed=reader.recover(
                journal,pages,quest_graph,approvals,actor_id=actor_id,
                scene_candidate_digest=scene_candidate_digest)
        successful_restarts+=1
        if (resumed["frame"]!=target
            or resumed["checkpoint"]!=batch["head_checkpoint"]
            or resumed["vault_receipt_digest"]!=saved_root):
            raise NativeSessionVaultError("post-restart game save replay changed")
        measured_cycle_ns=time.monotonic_ns()-cycle_start_ns
        database_bytes=sum(
            file.stat().st_size for file in (
                vault_path,Path(str(vault_path)+"-wal"),Path(str(vault_path)+"-shm"))
            if file.exists())
        if (max_cycle_ms is not None and measured_cycle_ns>max_cycle_ms*1_000_000):
            raise NativeSessionVaultError("measured game restart cycle exceeded wall clock budget")
        if max_vault_bytes is not None and database_bytes>max_vault_bytes:
            raise NativeSessionVaultError("measured game vault exceeded disk growth budget")
        item={
            "cycle":cycle+1,"source_head_frame":head,
            "cycle_wall_elapsed_ns":measured_cycle_ns,
            "cycle_vault_disk_bytes":database_bytes,
            "replayed_through":target,
            "game_checkpoint_digest":batch["head_checkpoint"]["receipt_digest"],
            "vault_receipt_digest":saved_root,
            "new_save":not commit["reused_existing"],
            "injected_rollback_before_commit":(
                bool(crash_interval and (cycle+1)%crash_interval==0
                     and target>last_frame)),
            "vault_retained_snapshots":rotate["retained_snapshots"],
            "vault_ancestry_receipts":rotate["archived_receipts"],
            "cold_recovery_audit_digest":resumed["independent_cold_audit_digest"],
        }
        item["receipt_digest"]=_sha(item)
        journal_rows.append(item)
        last_frame=target
    if last_frame!=head or successful_restarts!=cycles:
        raise NativeSessionVaultError("incomplete endurance source coverage")
    elapsed=time.monotonic_ns()-first
    checkpoint=journal_rows[-1]
    return_data={
        "schema":"skeleton.game.native_quest_endurance_evidence.v1",
        "actor_id":actor_id,"track":journal.track,
        "signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "cycles_executed":successful_restarts,
        "crash_rollbacks_executed":failures_injected,
        "new_checkpoints_committed":committed_saves,
        "idempotent_duplicate_saves":duplicate_saves,
        "source_frames_cold_replayed":head+1,
        "source_head_frame":head,
        "final_quest_checkpoint_digest":checkpoint["game_checkpoint_digest"],
        "final_vault_receipt_digest":saved_root,
        "on_disk_vault_bytes":vault_path.stat().st_size,
        "measured_elapsed_ns":elapsed,
        "peak_cycle_elapsed_ns":max(x["cycle_wall_elapsed_ns"] for x in journal_rows),
        "peak_measured_vault_disk_bytes":max(x["cycle_vault_disk_bytes"] for x in journal_rows),
        "max_cycle_ms":max_cycle_ms,
        "max_vault_bytes":max_vault_bytes,
        "cycle_evidence":journal_rows,
        "authority":"measured_bounded_restart_and_replay_not_months_long_uptime_certificate",
    }
    return_data["receipt_digest"]=_sha(return_data)
    return return_data
