"""Dragon's evidence-limited multi-game playthrough and comparative learning lab.

Can examine up to ten *original authored* games per call, execute actual
routes, independently replay the game state, grade design diversity and
propose improvements. Produces scoped learning notes, NOT neural weight
changes, real-world experience, copyrighted title synthesis or fabricated
native engine receipts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable,Sequence

from .game_frontier_expedition import (
    ExpeditionError,ExpeditionWorld,Traveler,
    find_route,alternative_routes,verify_route,ExpeditionEpisode,
    ExpeditionAction,_digest,
)

SCHEMA="skeleton.dragon.expedition_gameplay_lab.v1"
_GOALS=("fastest","safest","energy","scenic")


@dataclass(frozen=True,slots=True)
class DragonLesson:
    game_digest:str
    topic:str
    severity:str
    evidence_receipt:str
    recommendation:str

    def __post_init__(self):
        if self.topic not in {"path_diversity","fatigue","weather","quest_continuity","route_safety"}:
            raise ExpeditionError("Dragon topic unsupported")
        if self.severity not in {"observation","improvement","blocker"}:
            raise ExpeditionError("Dragon critique needs measured severity")
        if len(self.game_digest)!=64 or len(self.evidence_receipt)!=64:
            raise ExpeditionError("Dragon insight must reference exact gameplay evidence")
        if not isinstance(self.recommendation,str) or not 1<=len(self.recommendation)<=500:
            raise ExpeditionError("Dragon notes must be bounded original recommendations")


def _second_verifier(world:ExpeditionWorld,player:Traveler,route)->dict:
    """Independently execute *each edge*, rather than trusting route metadata."""
    episode=ExpeditionEpisode(world,player)
    steps=[]
    for key in route.edge_ids:
        if key not in world.by_edge or world.by_edge[key].source!=episode.position:
            raise ExpeditionError("Dragon's route proposed a disconnected game jump")
        result=episode.step(ExpeditionAction("travel",key))
        steps.append(result["receipt"])
    if not episode.won or episode.position!=route.destination:
        raise ExpeditionError("Dragon's second reviewer could not win the game")
    return {"game_head":episode.snapshot()["receipt_head"],"actions":len(steps),
            "state":episode.state(),"receipt":_digest(steps)}


def observe_original_games(
    worlds:Sequence[ExpeditionWorld],player:Traveler, *,
    alternative_budget:int=4,
)->dict:
    if (not isinstance(worlds,(tuple,list)) or not 1<=len(worlds)<=10
            or any(not isinstance(w,ExpeditionWorld) for w in worlds)
            or len({w.digest for w in worlds})!=len(worlds)):
        raise ExpeditionError("Dragon requires one to ten unique original game sources")
    if not isinstance(player,Traveler) or type(alternative_budget) is not int or not 1<=alternative_budget<=8:
        raise ExpeditionError("Dragon requires typed player and finite review budget")
    games=[]
    lessons=[]
    for world in worlds:
        goal=world.destinations[0]
        outcomes=[]
        paths=alternative_routes(world,player,goal,limit=alternative_budget)
        if not paths:
            raise ExpeditionError("Dragon game candidate has no actual travel route")
        for objective in _GOALS:
            route=find_route(world,player,goal,objective=objective)
            one=verify_route(world,player,route)
            two=_second_verifier(world,player,route)
            if (one["receipt_head"]!=two["game_head"]
                    or one["final_state"]!=two["state"]
                    or len(one["step_receipts"])!=two["actions"]):
                raise ExpeditionError("Dragon adversarial replay disagreed with source")
            outcomes.append({
                "objective":objective,"route_digest":route.digest,
                "duration_s":route.seconds,"energy":route.stamina,
                "damage":route.damage,"scenic_score":route.scenic_score,
                "steps":len(route.edge_ids),"first_reviewer":one["receipt_head"],
                "second_reviewer":two["game_head"],
                "evidence_receipt":two["receipt"],
            })
        row={
            "game_digest":world.digest,"project_id":world.project_id,
            "actual_route_alternatives":len(paths),
            "objective_outcomes":outcomes,
            "native_engine_playthroughs":0,
            "live_video_observed":False,"weight_training_completed":False,
        }
        row["receipt_digest"]=_digest(row)
        games.append(row)
        source=row["receipt_digest"]
        if len(paths)<2:
            lessons.append(DragonLesson(
                world.digest,"path_diversity","improvement",source,
                "Author a second traversable shortcut, bypass or scenic return route."))
        if max(x["energy"] for x in outcomes)>player.max_stamina*0.8:
            lessons.append(DragonLesson(
                world.digest,"fatigue","improvement",source,
                "Place a source-authorized safe rest point before the exhaustion corridor."))
        if any(x["damage"]>=50 for x in outcomes):
            lessons.append(DragonLesson(
                world.digest,"route_safety","blocker",source,
                "Re-author hazard levels or provide a visibly signposted safer route."))
        if world.weather.visibility<0.12:
            lessons.append(DragonLesson(
                world.digest,"weather","observation",source,
                "Retain explicit navigation equipment gates in low visibility."))
        if not any(x.quest_flag for x in world.waypoints):
            lessons.append(DragonLesson(
                world.digest,"quest_continuity","improvement",source,
                "Give one authored encounter a persistent quest flag and replay receipt."))
    metrics={
        "games_replayed":len(games),
        "verified_objective_routes":4*len(games),
        "route_alternatives":sum(g["actual_route_alternatives"] for g in games),
        "average_fastest_seconds":round(
            sum(g["objective_outcomes"][0]["duration_s"] for g in games)/len(games),4,
        ),
        "games_with_unsafe_routes":sum(
            any(outcome["damage"]>=50 for outcome in g["objective_outcomes"])
            for g in games
        ),
    }
    report={
        "schema":SCHEMA,"metrics":metrics,"game_evidence":games,
        "lessons":[vars(item) if hasattr(item,"__dict__") else {
            "game_digest":item.game_digest,"topic":item.topic,
            "severity":item.severity,"evidence_receipt":item.evidence_receipt,
            "recommendation":item.recommendation,
        } for item in lessons],
        "homebrew_only":True,"training_weight_promotion_allowed":False,
        "copyright_clearance_inferred":False,
        "peer_review_satisfied":False,
    }
    report["receipt_digest"]=_digest(report)
    return report


def verify_dragon_report(report:dict,worlds:Sequence[ExpeditionWorld],
                         player:Traveler, *,alternative_budget:int=4)->None:
    if not isinstance(report,dict) or report.get("schema")!=SCHEMA:
        raise ExpeditionError("Dragon report must be an original gameplay record")
    expected=observe_original_games(worlds,player,alternative_budget=alternative_budget)
    if report!=expected:
        raise ExpeditionError("Dragon learning record differs from actual gameplay evidence")
