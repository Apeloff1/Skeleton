"""Source-bound controller latency, event loss and accessibility quality checks.

Timestamps must be supplied by a real clock/HID host to claim hardware
results. Synthetic or simulated samples are accepted only as replay tests,
with hardware qualification explicitly forbidden in their receipts.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from math import isfinite
from typing import Iterable
from .game_frontier_expedition import ExpeditionError,_digest
from .game_frontier_expedition_controllers import ControllerProfile

@dataclass(frozen=True,slots=True)
class InputObservation:
    sequence:int
    frame:int
    action:str
    press_us:int
    dispatched_us:int
    observed_us:int
    source:str="simulation"
    device:int=0
    def __post_init__(self):
        if type(self.sequence) is not int or not 1<=self.sequence<=100000:
            raise ExpeditionError("controller latency event sequence invalid")
        if type(self.frame) is not int or not 0<=self.frame<=10**10:
            raise ExpeditionError("controller latency source frame invalid")
        if not isinstance(self.action,str) or not self.action.isidentifier():
            raise ExpeditionError("controller latency action identity invalid")
        if (any(type(t) is not int or t<0 or t>10**16
                for t in (self.press_us,self.dispatched_us,self.observed_us))
                or not self.press_us<=self.dispatched_us<=self.observed_us):
            raise ExpeditionError("controller latency event timestamps cannot go backward")
        if self.source not in ("simulation","device_host_clock"):
            raise ExpeditionError("controller latency evidence origin invalid")
        if type(self.device) is not int or not 0<=self.device<8:
            raise ExpeditionError("controller latency device id invalid")


def qualify_game_controller(
    profile:ControllerProfile,events:tuple[InputObservation,...], *,
    world_digest:str,max_end_to_end_us:int=30000,
    requires_hardware:bool=False,
)->dict:
    if (not isinstance(profile,ControllerProfile) or type(events) is not tuple
            or not 2<=len(events)<=10000
            or any(not isinstance(e,InputObservation) for e in events)):
        raise ExpeditionError("controller QA requires finite actual source observations")
    if type(world_digest) is not str or len(world_digest)!=64:
        raise ExpeditionError("controller QA requires exact original game source")
    if type(max_end_to_end_us) is not int or not 100<=max_end_to_end_us<=1_000_000:
        raise ExpeditionError("controller latency threshold invalid")
    if type(requires_hardware) is not bool:
        raise ExpeditionError("hardware qualification flag must be explicit")
    actions={x.action for x in profile.buttons}
    if any(e.action not in actions for e in events):
        raise ExpeditionError("controller QA action unbound in original game")
    if any(b.sequence!=a.sequence+1 or b.frame<a.frame
           or b.press_us<a.press_us for a,b in zip(events,events[1:])):
        raise ExpeditionError("controller input observations missing or reordered")
    if len({e.device for e in events})!=1:
        raise ExpeditionError("controller QA mixed physical device slots")
    if requires_hardware and any(e.source!="device_host_clock" for e in events):
        raise ExpeditionError("controller hardware certification cannot use simulated timestamps")
    latencies=[e.observed_us-e.press_us for e in events]
    sorted_latency=sorted(latencies)
    p95=sorted_latency[(95*(len(sorted_latency)-1)+99)//100]
    distribution={
        "min_us":min(latencies),"p50_us":sorted_latency[len(sorted_latency)//2],
        "p95_us":p95,"max_us":max(latencies),
        "average_us":round(sum(latencies)/len(latencies),3),
    }
    result={"schema":"skeleton.game.controller_latency_qa.v1",
            "world_digest":world_digest,"profile_digest":profile.digest,
            "source":sorted({e.source for e in events}),
            "device":events[0].device,
            "observed_events":len(events),
            "observed_action_types":sorted({e.action for e in events}),
            "timestamps":[asdict(e) for e in events],
            "threshold_us":max_end_to_end_us,
            "latency":distribution,
            "latency_budget_met":p95<=max_end_to_end_us,
            "hardware_clock_claim":requires_hardware,
            "full_hardware_qualification":False,
            "independently_signed_observation_origin":False}
    result["receipt_digest"]=_digest(result)
    return result

def verify_game_controller(profile:ControllerProfile,
                           events:tuple[InputObservation,...],candidate:dict, *,
                           world_digest:str,max_end_to_end_us:int=30000,
                           requires_hardware:bool=False)->None:
    if candidate!=qualify_game_controller(
        profile,events,world_digest=world_digest,
        max_end_to_end_us=max_end_to_end_us,requires_hardware=requires_hardware,
    ):
        raise ExpeditionError("controller latency statistics falsified or source changed")

def simulated_controller_trace(profile:ControllerProfile, *,
                               count:int=12)->tuple[InputObservation,...]:
    if not isinstance(profile,ControllerProfile) or type(count) is not int or not 2<=count<=128:
        raise ExpeditionError("controller fixture count invalid")
    actions=tuple(b.action for b in profile.buttons)
    return tuple(InputObservation(
        i+1,i+1,actions[i%len(actions)],
        (i+1)*20_000,(i+1)*20_000+2_000,(i+1)*20_000+8_000+i*23,
        "simulation",0,
    ) for i in range(count))
