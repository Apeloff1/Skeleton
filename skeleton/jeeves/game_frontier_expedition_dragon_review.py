"""Independent adversarial scrutiny of Dragon's original game-learning notes.

A second, independently reconstructed set of authored playthroughs checks
metrics, receipts, source/game relationships and inferred recommendations.
It cannot promote actual model weights or claim a native game was played.
"""
from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping,Sequence

from .game_frontier_expedition import (
    ExpeditionError,ExpeditionWorld,Traveler,ExpeditionEpisode,
    ExpeditionAction,find_route,_digest,
)
from .game_frontier_expedition_dragon import observe_original_games


@dataclass(frozen=True,slots=True)
class DragonAdversaryPolicy:
    min_objectives:int=4
    min_route_alternatives:int=1
    max_games:int=10
    require_source_isolation:bool=True

    def __post_init__(self):
        if type(self.min_objectives) is not int or not 1<=self.min_objectives<=4:
            raise ExpeditionError("Dragon objective scrutiny budget invalid")
        if type(self.min_route_alternatives) is not int or not 1<=self.min_route_alternatives<=8:
            raise ExpeditionError("Dragon route diversity demand invalid")
        if type(self.max_games) is not int or not 1<=self.max_games<=10:
            raise ExpeditionError("Dragon game review budget invalid")
        if type(self.require_source_isolation) is not bool:
            raise ExpeditionError("Dragon source policy must be explicit")


def _independent_route(world:ExpeditionWorld,player:Traveler,objective:str)->dict:
    route=find_route(world,player,world.destinations[0],objective=objective)
    game=ExpeditionEpisode(world,player)
    direct=[]
    for edge_id in route.edge_ids:
        if edge_id not in world.by_edge or world.by_edge[edge_id].source!=game.position:
            raise ExpeditionError("Dragon proposed a disconnected path")
        direct.append(game.step(ExpeditionAction("travel",edge_id)))
    if not game.won:
        raise ExpeditionError("Dragon opponent could not complete original world")
    return {
        "objective":objective,"route_digest":route.digest,
        "source_digest":world.digest,"steps":len(direct),
        "receipt_head":game.snapshot()["receipt_head"],
        "time":route.seconds,"energy":route.stamina,
        "damage":route.damage,
    }


def adversarial_dragon_review(
    report:Mapping,worlds:Sequence[ExpeditionWorld],player:Traveler, *,
    policy:DragonAdversaryPolicy=DragonAdversaryPolicy(),
    alternative_budget:int=4,
)->dict:
    if not isinstance(report,Mapping) or not isinstance(player,Traveler) or not isinstance(policy,DragonAdversaryPolicy):
        raise ExpeditionError("Dragon challenger requires real observed source game")
    if (not isinstance(worlds,(list,tuple)) or not 1<=len(worlds)<=policy.max_games
            or any(not isinstance(w,ExpeditionWorld) for w in worlds)):
        raise ExpeditionError("Dragon challenger game scope exceeded")
    expected=observe_original_games(
        worlds,player,alternative_budget=alternative_budget,
    )
    if dict(report)!=expected:
        raise ExpeditionError("Dragon report differs from independently reproduced learning evidence")
    checks=[]
    observed=report["game_evidence"]
    for index,world in enumerate(worlds):
        row=observed[index]
        if (row["game_digest"]!=world.digest or
                len(row["objective_outcomes"])<policy.min_objectives or
                row["actual_route_alternatives"]<policy.min_route_alternatives):
            raise ExpeditionError("Dragon learning lacks required source route diversity")
        for claim in row["objective_outcomes"]:
            reviewed=_independent_route(world,player,claim["objective"])
            if (reviewed["receipt_head"]!=claim["first_reviewer"]
                    or reviewed["receipt_head"]!=claim["second_reviewer"]
                    or reviewed["route_digest"]!=claim["route_digest"]
                    or reviewed["time"]!=claim["duration_s"]
                    or reviewed["energy"]!=claim["energy"]
                    or reviewed["damage"]!=claim["damage"]):
                raise ExpeditionError("Dragon opponent disproved claimed game outcome")
            reviewed["evidence_receipt"]=_digest(reviewed)
            checks.append(reviewed)
    if policy.require_source_isolation and len({w.digest for w in worlds})!=len(worlds):
        raise ExpeditionError("Dragon comparison crossed duplicate/ambiguous source")
    evidence={
        "schema":"skeleton.dragon.adversarial_original_game_review.v1",
        "training_report":report["receipt_digest"],
        "source_games":[w.digest for w in worlds],
        "independent_playthroughs":len(checks),
        "replayed_route_evidence":checks,
        "approved_for_verified_learning_notes":True,
        "model_weights_updated":False,
        "native_games_executed":False,
        "real_video_frames_examined":0,
        "external_peer_review_satisfied":False,
    }
    evidence["receipt_digest"]=_digest(evidence)
    return evidence


def adversarial_attack_matrix(
    report:dict,worlds:Sequence[ExpeditionWorld],player:Traveler,
)->dict:
    """Challenge admission with modified metrics, routes, provenance and authority."""
    failures={}
    templates=(
        ("inflated_games",("metrics","games_replayed"),999),
        ("forged_weight_training",("training_weight_promotion_allowed",),True),
        ("native_laundering",("game_evidence",0,"native_engine_playthroughs"),10),
        ("altered_route",("game_evidence",0,"objective_outcomes",0,"damage"),999),
        ("corrupt_receipt",("receipt_digest",),"0"*64),
        ("copyright_claim",("copyright_clearance_inferred",),True),
    )
    for name,path,value in templates:
        candidate=deepcopy(report)
        pointer=candidate
        for key in path[:-1]:
            pointer=pointer[key]
        pointer[path[-1]]=value
        try:
            adversarial_dragon_review(candidate,worlds,player)
        except ExpeditionError:
            failures[name]="rejected"
        else:
            raise ExpeditionError("Dragon independent challenger accepted forged "+name)
    proof={
        "schema":"skeleton.dragon.adversarial_attack_matrix.v1",
        "source_digest":_digest([w.digest for w in worlds]),
        "original_report_receipt":report["receipt_digest"],
        "attacks":failures,"all_attacks_rejected":True,
        "automated_host_signoff":False,
    }
    proof["receipt_digest"]=_digest(proof)
    return proof
