"""Deterministic long-cycle expedition recovery exercising actual durable gameplay.

A bounded host pass executes real game actions, commits them to SQLite,
closes and reopens the store on every logical cycle, validates every replay
receipt and detects unexpected state changes. A logical cycle is *not*
proof of days, months or years of wall-clock runtime.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from .game_frontier_expedition import (
    ExpeditionAction,ExpeditionEpisode,ExpeditionError,
    ExpeditionWorld,Traveler,_digest,
)
from .game_frontier_expedition_save_store import (
    ExpeditionSaveStore,ExpeditionSaveConflict,
)


@dataclass(frozen=True,slots=True)
class EndurancePolicy:
    logical_cycles:int=30
    actions_per_cycle:int=5
    reopen_each_cycle:bool=True

    def __post_init__(self):
        if type(self.logical_cycles) is not int or not 1<=self.logical_cycles<=365:
            raise ExpeditionError("endurance host cycle count must be bounded 1..365")
        if type(self.actions_per_cycle) is not int or self.actions_per_cycle!=5:
            raise ExpeditionError("endurance verified scenario requires five real actions")
        if type(self.reopen_each_cycle) is not bool:
            raise ExpeditionError("endurance reopen policy must be explicit")


def _roundtrip(world:ExpeditionWorld)->tuple[ExpeditionAction,...]:
    outbound=world.by_edge.get("spire_footpath")
    reverse=world.by_edge.get("spire_footpath.reverse")
    if (outbound is None or reverse is None
            or outbound.source!=world.arrival
            or reverse.source!=outbound.target
            or reverse.target!=world.arrival
            or not world.by_id[outbound.target].landmark
            or not world.by_id[world.arrival].safe_rest):
        raise ExpeditionError("durable endurance needs an authored reversible rest corridor")
    return (
        ExpeditionAction("inspect"),
        ExpeditionAction("travel",outbound.edge_id),
        ExpeditionAction("interact"),
        ExpeditionAction("travel",reverse.edge_id),
        ExpeditionAction("rest"),
    )


def run_expedition_endurance(
    path:Path,run_id:str,world:ExpeditionWorld,traveler:Traveler, *,
    policy:EndurancePolicy=EndurancePolicy(),
)->dict:
    if (not isinstance(path,Path) or not isinstance(world,ExpeditionWorld)
            or not isinstance(traveler,Traveler)
            or not isinstance(policy,EndurancePolicy)):
        raise ExpeditionError("endurance requires typed existing game and durable target")
    actions=_roundtrip(world)
    if policy.logical_cycles*len(actions)>4096:
        raise ExpeditionError("endurance game history exceeds replay budget")
    progress=[]
    for iteration in range(policy.logical_cycles):
        # Each store reopen forces an actual SQLite recovery rather than an
        # in-memory-only test of the same Python instance.
        with ExpeditionSaveStore(path) as store:
            checkpoint=store.load(run_id,world,traveler)
            if checkpoint is None:
                if iteration!=0:
                    raise ExpeditionError("previous endurance checkpoint disappeared")
                saved=store.save(run_id,ExpeditionEpisode(world,traveler))
                checkpoint=saved
            if len(checkpoint.episode.actions)!=iteration*len(actions):
                raise ExpeditionError("endurance restore lost or duplicated real actions")
            episode=checkpoint.episode
            before=checkpoint.receipt
            for action in actions:
                result=episode.step(action)
                if result["done"] or result["state"]["health"]<=0:
                    raise ExpeditionError("endurance route unexpectedly terminated production")
            updated=store.save(
                run_id,episode,expected_generation=checkpoint.generation,
            )
            confirmed=store.load(run_id,world,traveler)
            if (confirmed is None or confirmed.generation!=updated.generation
                    or confirmed.episode.snapshot()!=episode.snapshot()):
                raise ExpeditionError("durable endurance checkpoint did not replay")
            row={
                "logical_cycle":iteration+1,
                "generation":updated.generation,
                "prior_save_receipt":before,
                "save_receipt":updated.receipt,
                "game_head":episode.snapshot()["receipt_head"],
                "actual_actions":len(episode.actions),
                "source_world":world.digest,
            }
            row["receipt_digest"]=_digest(row)
            progress.append(row)
    result={
        "schema":"skeleton.game.expedition_endurance.v1",
        "world_digest":world.digest,"source_digest":world.source_digest,
        "logical_cycles":policy.logical_cycles,
        "total_game_actions":policy.logical_cycles*5,
        "reopened_sqlite_sessions":policy.logical_cycles,
        "first_receipt":progress[0]["receipt_digest"],
        "last_receipt":progress[-1]["receipt_digest"],
        "cycles":progress,
        "real_gameplay_replay_per_cycle":True,
        "observed_wall_clock_days":0,
        "long_duration_qualification":False,
    }
    result["receipt_digest"]=_digest(result)
    return result
