"""Bounded multi-scenario *executed* expedition QA; no synthetic passes.

Runs original authored games with actual route solver and state machine under
contrasting environment and capability profiles. Evidence is deterministic
and source-bound, while hardware/quality/copyright signoff remains external.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import math
from typing import Sequence

from .game_frontier_expedition import (
    ExpeditionError, ExpeditionWeather, ExpeditionWorld, Traveler, _digest,
    find_route, alternative_routes, verify_route,
)
from .game_frontier_expedition_generation import (
    ArchipelagoProfile, author_archipelago,
)

SCHEMA="skeleton.game.frontier_expedition_qa.v1"


@dataclass(frozen=True,slots=True)
class QAScenario:
    scenario_id: str
    wind_mps: float
    rain: float
    visibility: float
    turbulence: float
    equipment_enabled: bool = True

    def __post_init__(self):
        if (not isinstance(self.scenario_id,str) or not 1<=len(self.scenario_id)<=60
                or any(ch not in "abcdefghijklmnopqrstuvwxyz_0123456789" for ch in self.scenario_id)):
            raise ExpeditionError("QA scenario identity must be exact")
        for name,lo,hi in (("wind_mps",-100,100),("rain",0,1),
                           ("visibility",0,1),("turbulence",0,1)):
            v=getattr(self,name)
            if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:
                raise ExpeditionError("QA scenario requires bounded weather")
        if type(self.equipment_enabled) is not bool:
            raise ExpeditionError("QA equipment toggle must be explicit")


QA_SCENARIOS=(
    QAScenario("clear",0,0,1,0),
    QAScenario("headwind",-20,0.2,0.8,0.2),
    QAScenario("tailwind",20,0,0.8,0.1),
    QAScenario("rain",5,1,0.7,0.4),
    QAScenario("turbulence",0,0.2,0.6,0.95),
    QAScenario("fog_with_instruments",0,0.3,0.03,0.3),
    QAScenario("fog_without_instruments",0,0.3,0.03,0.3,False),
)


def qa_player(scenario: QAScenario) -> Traveler:
    return Traveler(
        permitted_modes=frozenset((
            "walk","rope_bridge","updraft","glide","airship","portal",
            "climb","dive","swim","rail","boat")),
        flags=frozenset(("glider","airship_license","portal_key","diving_gear")),
        equipment=(frozenset(("instrument_navigation",)) if
                   scenario.equipment_enabled else frozenset()),
        max_stamina=1000,skill=0.8,carried_kg=5,capacity_kg=30,
    )


def run_expedition_qa(
    project_id: str, source_digest: str, *,
    seeds: Sequence[int]=(11,42,99), islands: int=9,
    scenarios: Sequence[QAScenario]=QA_SCENARIOS, alternatives: int=3,
) -> dict:
    if (not isinstance(seeds,(tuple,list)) or not 1<=len(seeds)<=32
            or any(type(v) is not int or not 0<=v<=2**63-1 for v in seeds)
            or len(set(seeds))!=len(seeds)):
        raise ExpeditionError("QA seed sample requires unique bounded seeds")
    if (not isinstance(scenarios,(tuple,list)) or not 1<=len(scenarios)<=16
            or any(not isinstance(x,QAScenario) for x in scenarios)
            or len({x.scenario_id for x in scenarios})!=len(scenarios)):
        raise ExpeditionError("QA scenario catalog requires unique typed cases")
    if type(alternatives) is not int or not 1<=alternatives<=8:
        raise ExpeditionError("QA alternative route count must be bounded")
    rows=[]
    total_routes=0
    for seed in seeds:
        for scenario in scenarios:
            weather=ExpeditionWeather(
                wind_x_mps=scenario.wind_mps,
                rain=scenario.rain,visibility=scenario.visibility,
                turbulence=scenario.turbulence,
            )
            world=author_archipelago(
                project_id,source_digest,ArchipelagoProfile(
                    seed=seed,islands=islands,
                ),weather=weather,
            )
            traveler=qa_player(scenario)
            record={
                "seed":seed,"scenario":scenario.scenario_id,
                "world_digest":world.digest,
                "traveler_digest":_digest({
                    "flags":sorted(traveler.flags),
                    "equipment":sorted(traveler.equipment),
                    "modes":sorted(traveler.permitted_modes),
                    "stamina":traveler.max_stamina,
                }),
                "routes_executed":0,"route_receipts":[],
                "route_times_seconds":[],
                "blocked":False,"block_reason":None,
                "native_executed":False,
            }
            try:
                routes=alternative_routes(
                    world,traveler,world.destinations[0],limit=alternatives,
                )
                for route in routes:
                    evidence=verify_route(world,traveler,route)
                    if not evidence["verified"] or not evidence["final_state"]["won"]:
                        raise ExpeditionError("simulation failed authored destination")
                    record["routes_executed"]+=1
                    record["route_receipts"].append(evidence["receipt_head"])
                    record["route_times_seconds"].append(route.seconds)
                    total_routes+=1
            except ExpeditionError as exc:
                if str(exc)!="no traversable route under current abilities and stamina":
                    raise
                record["blocked"]=True
                record["block_reason"]="unreachable_under_authorized_capabilities"
            if not record["blocked"] and record["routes_executed"]<1:
                raise ExpeditionError("QA found neither a source route nor an explicit blocker")
            record["receipt_digest"]=_digest(record)
            rows.append(record)
    report={
        "schema":SCHEMA,"project":project_id,
        "source_digest":source_digest,"seed_count":len(seeds),
        "scenario_count":len(scenarios),"cases_executed":len(rows),
        "executed_game_routes":total_routes,
        "blocked_cases":sum(row["blocked"] for row in rows),
        "cases":rows,
        "release_approved":False,
        "physical_engine_playthroughs":0,
    }
    report["receipt_digest"]=_digest(report)
    return report


def compare_expedition_qa(left:dict,right:dict)->dict:
    for candidate in (left,right):
        if (not isinstance(candidate,dict) or candidate.get("schema")!=SCHEMA
                or candidate.get("receipt_digest")!=_digest({
                    k:v for k,v in candidate.items() if k!="receipt_digest"
                })):
            raise ExpeditionError("QA comparison requires verified original reports")
    if left["source_digest"]!=right["source_digest"]:
        raise ExpeditionError("cannot compare QA across unrelated source snapshots")
    metrics={
        "route_count_change":right["executed_game_routes"]-left["executed_game_routes"],
        "newly_blocked_cases":right["blocked_cases"]-left["blocked_cases"],
        "case_count_change":right["cases_executed"]-left["cases_executed"],
        "same_source":True,
        "comparative_score_only":True,
    }
    metrics["receipt_digest"]=_digest({
        "left":left["receipt_digest"],"right":right["receipt_digest"],
        "metrics":metrics,
    })
    return metrics
