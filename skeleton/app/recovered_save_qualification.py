"""Physically reopen isolated SQLite project bundles and verify recovered replay.

The qualification writes only to a fresh temporary private directory.
No existing project workspace, live database, release location or Git
checkout is changed. No cross-process or crash-loss guarantee is implied.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from skeleton.app.recovered_evidence import EvidenceError, canonical, digest, seal, parse, read_document
from skeleton.ai.game_builder.project_bundle.project_save import ProjectSaver
from skeleton.ai.game_builder.project_bundle.history import ProjectHistory
from skeleton.ai.game_builder.project_bundle.project_diff import diff_sequences
from skeleton.kernel.game_save_plane import GameSavePlane
from skeleton.persistence.game_save_sqlite import (
    open_game_save_db, SqliteCheckpointStore, SqliteReplayJournal,
)
from skeleton.game.simulation.fixed_input_replay import Simulation, qualify_motion
from skeleton.ai.game_builder.synthesized_quest_runtime import Campaign, qualify_campaign, solution


def _files(order,save,plan=None):
    files={"replay/order.json":canonical(order).decode("ascii"),
           "replay/save.json":canonical(save).decode("ascii")}
    if plan is not None:
        files["replay/plan.json"]=canonical(plan).decode("ascii")
    return files


def _restore(kind,order,plan,save):
    if kind=="movement":
        return Simulation.restore(order,save,expected_digest=save["digest"],authorized=True)
    return Campaign.restore(order,plan,save,expected_plan_digest=plan["digest"],
                            expected_save_digest=save["digest"],authorized=True)


def _load(version,expected_order,expected_save,expected_plan=None):
    order=parse(version.files["replay/order.json"].encode("ascii"))
    save=parse(version.files["replay/save.json"].encode("ascii"))
    plan=None
    if expected_plan is not None:
        plan=parse(version.files["replay/plan.json"].encode("ascii"))
    if order!=expected_order or save!=expected_save or plan!=expected_plan:
        raise EvidenceError("restored project source differs")
    return order,plan,save


def _prepare(kind, order):
    if kind=="movement":
        receipt=qualify_motion(order,authorized=True)
        checkpoint=receipt["checkpoint"]
        events=order["frames"]
        return None,checkpoint,receipt["final"],events,checkpoint["frames"]
    if kind=="quest":
        receipt=qualify_campaign(order,authorized=True)
        plan=receipt["plan"]
        events=solution(plan)
        split=len(events)//2
        run=Campaign.start(order,plan,expected_plan_digest=plan["digest"],authorized=True)
        for event in events[:split]:
            run.apply(event)
        checkpoint=run.snapshot()
        if checkpoint["digest"]!=receipt["checkpoint_digest"]:
            raise EvidenceError("quest midpoint differs")
        return plan,checkpoint,receipt["final"],events,split
    raise EvidenceError("unknown replay kind")


def qualify_storage(kind,order,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit local save qualification required")
    plan,checkpoint,final,events,split=_prepare(kind,order)
    # Use a fixed bounded project identity; the database is unique per run.
    project="recovered-replay"
    genre="adventure"
    with TemporaryDirectory(prefix="skeleton-recovery-") as directory:
        db=str(Path(directory)/"qualification.sqlite3")
        manifests=[]
        connection=open_game_save_db(db)
        try:
            saver=ProjectSaver(GameSavePlane(store=SqliteCheckpointStore(connection,retain=8)))
            journal=SqliteReplayJournal(connection,project)
            for index,event in enumerate(events[:split]):
                journal.append(index,{"input":event})
            first=saver.save_files(project,genre,_files(order,checkpoint,plan),label="midpoint")
            manifests.append(first.payload())
            first_journal=journal.head_digest()
        finally:
            connection.close()
        connection=open_game_save_db(db)
        try:
            saver=ProjectSaver(GameSavePlane(store=SqliteCheckpointStore(connection,retain=8)))
            journal=SqliteReplayJournal(connection,project)
            if journal.head_digest()!=first_journal or journal.frames()!=[
                (i,{"input":event}) for i,event in enumerate(events[:split])
            ]:
                raise EvidenceError("reopened journal prefix differs")
            version=saver.load(project,sequence=first.sequence)
            if version.manifest.payload()!=first.payload():
                raise EvidenceError("reopened project manifest differs")
            restored_order,restored_plan,restored_save=_load(version,order,checkpoint,plan)
            run=_restore(kind,restored_order,restored_plan,restored_save)
            for index,event in enumerate(events[split:],split):
                if kind=="movement":
                    run.frame()
                else:
                    run.apply(event)
                journal.append(index,{"input":event})
            if run.snapshot()!=final:
                raise EvidenceError("continued replay differs")
            last=saver.save_files(project,genre,_files(order,final,plan),label="completed")
            manifests.append(last.payload())
            final_journal=journal.head_digest()
        finally:
            connection.close()
        connection=open_game_save_db(db)
        try:
            saver=ProjectSaver(GameSavePlane(store=SqliteCheckpointStore(connection,retain=8)))
            journal=SqliteReplayJournal(connection,project)
            if journal.head_digest()!=final_journal or journal.frames()!=[
                (i,{"input":event}) for i,event in enumerate(events)
            ]:
                raise EvidenceError("reopened complete journal differs")
            current=saver.load(project,sequence=last.sequence)
            if current.manifest.payload()!=last.payload():
                raise EvidenceError("final project manifest differs")
            restored_order,restored_plan,restored_save=_load(current,order,final,plan)
            if _restore(kind,restored_order,restored_plan,restored_save).snapshot()!=final:
                raise EvidenceError("final replay differs")
            difference=diff_sequences(saver,project,first.sequence,last.sequence)
            history=ProjectHistory(saver)
            history_before=[asdict(row) for row in history.versions(project)]
            rollback=history.rollback(project,first.sequence)
            if rollback["files_match"] is not True or rollback["new_head"]<=last.sequence:
                raise EvidenceError("append-only rollback failed")
            rolled=saver.load(project,sequence=rollback["new_head"])
            if rolled.files!=version.files:
                raise EvidenceError("rollback bytes differ")
            manifests.append(rolled.manifest.payload())
            rollback_sequence=rollback["new_head"]
            history_after=[asdict(row) for row in history.versions(project)]
        finally:
            connection.close()
        connection=open_game_save_db(db)
        try:
            saver=ProjectSaver(GameSavePlane(store=SqliteCheckpointStore(connection,retain=8)))
            rolled=saver.load(project,sequence=rollback_sequence)
            if rolled.manifest.payload()!=manifests[-1]:
                raise EvidenceError("reopened rollback manifest differs")
            ro,rp,rs=_load(rolled,order,checkpoint,plan)
            if _restore(kind,ro,rp,rs).snapshot()!=checkpoint:
                raise EvidenceError("reopened rollback replay differs")
            if saver.load(project,sequence=last.sequence).files!=current.files:
                raise EvidenceError("rollback destroyed prior version")
        finally:
            connection.close()
    return seal({"schema":"skeleton.recovered-save.qualification.v1","kind":kind,
                 "order_digest":digest(order),"midpoint_digest":checkpoint["digest"],
                 "final_digest":final["digest"],"versions":manifests,
                 "journal_prefix_digest":first_journal,"journal_final_digest":final_journal,
                 "journal_event_count":len(events),"file_diff":difference,
                 "history_before_rollback":history_before,"history_after_rollback":history_after,
                 "rollback":rollback,"sqlite_connections_reopened":3,
                 "sqlite_disk_roundtrip_executed":True,"prior_version_retained":True,
                 "cross_process_restart_tested":False,"crash_recovery_tested":False,
                 "native_engine_executed":False,"release_certified":False})


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind",choices=("movement","quest"))
    parser.add_argument("--order",required=True)
    parser.add_argument("--trusted-local-operator",action="store_true")
    args=parser.parse_args(argv)
    try:
        if not args.trusted_local_operator:
            raise PermissionError("explicit operator required")
        order,_=read_document(args.order)
        print(canonical(qualify_storage(args.kind,order,authorized=True)).decode("ascii"))
        return 0
    except (ValueError,PermissionError,TypeError,KeyError,OSError,RuntimeError) as exc:
        print(json.dumps({"ok":False,"error":type(exc).__name__}),file=sys.stderr)
        return 2
