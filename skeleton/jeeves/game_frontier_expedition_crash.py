"""Controlled crash-injection, exactly-once replay and durable game recovery.

Exercises real SQLite-backed travel/interaction/rest under simulated host
faults before commit and after commit-before-ack. Observes persistent source
state on every restart and refuses duplicated actions or silent rollbacks.
These are deterministic *fault simulations*, not measured months of uptime.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .game_frontier_expedition import (
    ExpeditionAction,ExpeditionEpisode,ExpeditionError,ExpeditionWorld,Traveler,_digest,
)
from .game_frontier_expedition_save_store import (
    ExpeditionSaveStore,ExpeditionSaveConflict,
)
from .game_frontier_expedition_endurance import _roundtrip


@dataclass(frozen=True, slots=True)
class CrashPolicy:
    game_cycles:int=5
    crash_before_commit_every:int=3
    crash_after_commit_every:int=4
    max_retries_per_action:int=3

    def __post_init__(self):
        for attr,minimum,maximum in (
            ("game_cycles",1,100),
            ("crash_before_commit_every",2,1000),
            ("crash_after_commit_every",2,1000),
            ("max_retries_per_action",1,10),
        ):
            val=getattr(self,attr)
            if type(val) is not int or not minimum<=val<=maximum:
                raise ExpeditionError("crash injection policy outside finite safety budget")


def exercise_game_crash_recovery(
    path:Path,world:ExpeditionWorld,player:Traveler, *,
    run_id:str="crash_qualification",
    policy:CrashPolicy=CrashPolicy(),
)->dict:
    if (not isinstance(path,Path) or not isinstance(world,ExpeditionWorld)
            or not isinstance(player,Traveler) or not isinstance(policy,CrashPolicy)):
        raise ExpeditionError("fault harness requires typed game, player and durable file")
    actions=_roundtrip(world)
    if len(actions)*policy.game_cycles>500:
        raise ExpeditionError("crash-test action budget exceeded")
    if path.exists() or path.is_symlink():
        raise ExpeditionError("fault harness refuses to overwrite existing run")
    timeline=[]
    crashes=0
    reconciliations=0
    with ExpeditionSaveStore(path) as store:
        store.save(run_id,ExpeditionEpisode(world,player))
    for index in range(policy.game_cycles*len(actions)):
        action=actions[index%len(actions)]
        retries=0
        expected_game_actions=index
        while True:
            retries+=1
            if retries>policy.max_retries_per_action+1:
                raise ExpeditionError("durable retry budget exhausted")
            with ExpeditionSaveStore(path) as store:
                old=store.load(run_id,world,player)
                if old is None:
                    raise ExpeditionError("crash recovery lost original game source")
                if len(old.episode.actions)==index+1:
                    # This was committed but its host acknowledgement was lost.
                    reconciliations+=1
                    timeline.append({
                        "action_index":index+1,"effect":"recovered_committed_action",
                        "generation":old.generation,
                        "game_head":old.episode.snapshot()["receipt_head"],
                        "save_receipt":old.receipt,
                    })
                    break
                if len(old.episode.actions)!=expected_game_actions:
                    raise ExpeditionError("crash recovery replay has extra/missing action")
                candidate=old.episode
                candidate.step(action)
                target_game_head=candidate.snapshot()["receipt_head"]
                # Inject at most once for each action to permit an observed
                # rerun while still exercising a genuine lost host call.
                before=(index+1)%policy.crash_before_commit_every==0
                after=(index+1)%policy.crash_after_commit_every==0
                if retries==1 and before:
                    crashes+=1
                    timeline.append({
                        "action_index":index+1,"effect":"crash_before_commit",
                        "generation":old.generation,
                        "game_head":old.episode.snapshot()["receipt_head"],
                        "save_receipt":old.receipt,
                    })
                    continue
                new=store.save(
                    run_id,candidate,expected_generation=old.generation,
                )
                if retries==1 and after:
                    crashes+=1
                    timeline.append({
                        "action_index":index+1,"effect":"crash_after_commit_before_ack",
                        "generation":new.generation,
                        "game_head":target_game_head,
                        "save_receipt":new.receipt,
                    })
                    continue
                if new.episode.snapshot()["receipt_head"]!=target_game_head:
                    raise ExpeditionError("game state changed during durable CAS commit")
                timeline.append({
                    "action_index":index+1,"effect":"acknowledged",
                    "generation":new.generation,
                    "game_head":target_game_head,
                    "save_receipt":new.receipt,
                })
                break
    with ExpeditionSaveStore(path) as store:
        actual=store.load(run_id,world,player)
        expected=policy.game_cycles*len(actions)
        if actual is None or len(actual.episode.actions)!=expected:
            raise ExpeditionError("final crashed game missing committed actions")
        history=store.history(run_id)
        if len(history)!=expected+1 or actual.generation!=expected+1:
            raise ExpeditionError("durable crash recovery introduced duplicate save generations")
        final=actual.episode.snapshot()
    report={
        "schema":"skeleton.game.crash_recovery_qualification.v1",
        "world_digest":world.digest,"source_digest":world.source_digest,
        "game_actions":expected,"sqlite_generations":len(history),
        "injected_crashes":crashes,"reconciled_lost_acks":reconciliations,
        "history_head":history[-1]["receipt_digest"],
        "game_head":final["receipt_head"],
        "faults":timeline,
        "exactly_once_gameplay_replayed":True,
        "real_process_crashes_observed":False,
        "actual_wall_clock_endurance_days":0,
        "release_approved":False,
    }
    report["receipt_digest"]=_digest(report)
    return report
