"""Bounded months-scale logical production watchdog and hash-linked telemetry.

Tracks caller-observed CPU/RAM/disk/head progress with explicit simulated vs
measured provenance, stalls and recovery actions. A 365-day logical plan is
NOT 365 days of measured uptime. All events are independently reproducible.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from math import isfinite
from .game_frontier_expedition import ExpeditionError,_digest

@dataclass(frozen=True,slots=True)
class ProductionBudget:
    max_rss_mb:int=4096
    max_cpu_pct:float=95.
    min_free_disk_mb:int=512
    max_no_progress_ticks:int=12
    max_telemetry_rows:int=50000
    def __post_init__(self):
        if any(type(v) is not int for v in (
                self.max_rss_mb,self.min_free_disk_mb,
                self.max_no_progress_ticks,self.max_telemetry_rows)):
            raise ExpeditionError("production resource budgets must be integers")
        if (not 64<=self.max_rss_mb<=1_000_000
                or not 1<=self.min_free_disk_mb<=1_000_000
                or not 1<=self.max_no_progress_ticks<=10000
                or not 1<=self.max_telemetry_rows<=50000
                or type(self.max_cpu_pct) not in (int,float)
                or not isfinite(self.max_cpu_pct) or not 1<=self.max_cpu_pct<=100):
            raise ExpeditionError("production watchdog budget invalid")

@dataclass(frozen=True,slots=True)
class ResourceSample:
    tick:int
    rss_mb:int
    cpu_pct:float
    disk_free_mb:int
    work_receipt:str
    origin:str="simulation"
    def __post_init__(self):
        if type(self.tick) is not int or not 1<=self.tick<=10**10:
            raise ExpeditionError("work telemetry sequence invalid")
        if (type(self.rss_mb) is not int or not 0<=self.rss_mb<=1_000_000
                or type(self.disk_free_mb) is not int or not 0<=self.disk_free_mb<=10**9):
            raise ExpeditionError("resource telemetry quantities invalid")
        if type(self.cpu_pct) not in (int,float) or not isfinite(self.cpu_pct) or not 0<=self.cpu_pct<=100:
            raise ExpeditionError("resource telemetry CPU sample invalid")
        if type(self.work_receipt) is not str or len(self.work_receipt)!=64:
            raise ExpeditionError("production watchdog requires verified source head")
        if self.origin not in ("simulation","host_process_meter"):
            raise ExpeditionError("production telemetry has unsupported measurement provenance")

class ProductionWatchdog:
    def __init__(self,world_digest:str,policy:ProductionBudget=ProductionBudget()):
        if type(world_digest) is not str or len(world_digest)!=64 or not isinstance(policy,ProductionBudget):
            raise ExpeditionError("production monitor requires original game source")
        self.world_digest=world_digest
        self.policy=policy
        self.history=[]
        self.head=_digest({"world":world_digest,"budget":asdict(policy),"genesis":True})
        self.last_work=""
        self.idle=0
        self.halted=False

    def observe(self,sample:ResourceSample)->dict:
        if not isinstance(sample,ResourceSample):
            raise ExpeditionError("production monitor requires a typed resource observation")
        if self.halted:
            raise ExpeditionError("production watchdog halted; explicit owner recovery required")
        if len(self.history)>=self.policy.max_telemetry_rows:
            raise ExpeditionError("production telemetry exceeded bounded journal")
        if sample.tick!=len(self.history)+1:
            raise ExpeditionError("production telemetry missing or duplicated tick")
        if sample.work_receipt==self.last_work:
            self.idle+=1
        else:
            self.idle=0
        self.last_work=sample.work_receipt
        causes=[]
        if sample.rss_mb>self.policy.max_rss_mb:
            causes.append("memory")
        if sample.cpu_pct>self.policy.max_cpu_pct:
            causes.append("cpu")
        if sample.disk_free_mb<self.policy.min_free_disk_mb:
            causes.append("disk")
        if self.idle>=self.policy.max_no_progress_ticks:
            causes.append("stalled")
        if causes:
            self.halted=True
        old=self.head
        row={"schema":"skeleton.game.production_telemetry.v1",
             "world":self.world_digest,"observation":asdict(sample),
             "prior":old,"idle_ticks":self.idle,
             "violations":causes,"action":"halt_for_host_review" if causes else "continue",
             "claimed_real_uptime_days":0}
        self.head=_digest(row)
        result={**row,"receipt_digest":self.head}
        self.history.append(result)
        return result

    def snapshot(self)->dict:
        data={"schema":"skeleton.game.production_watchdog.v1",
              "world":self.world_digest,"policy":asdict(self.policy),
              "history":list(self.history),"head":self.head,
              "halted":self.halted,"idle":self.idle,
              "last_work":self.last_work,"actual_months_observed":0,
              "model_weights_changed":False}
        return {**data,"snapshot_digest":_digest(data)}

    @classmethod
    def restore(cls,world_digest:str,snapshot:dict)->"ProductionWatchdog":
        if not isinstance(snapshot,dict) or snapshot.get("schema")!="skeleton.game.production_watchdog.v1":
            raise ExpeditionError("production telemetry snapshot invalid")
        data=dict(snapshot)
        if data.pop("snapshot_digest",None)!=_digest(data):
            raise ExpeditionError("production telemetry checksum mismatch")
        policy=ProductionBudget(**snapshot["policy"])
        instance=cls(world_digest,policy)
        if (snapshot["world"]!=world_digest or not isinstance(snapshot["history"],list)
                or len(snapshot["history"])>policy.max_telemetry_rows):
            raise ExpeditionError("production watchdog source/size changed")
        for event in snapshot["history"]:
            if event!=instance.observe(ResourceSample(**event["observation"])):
                raise ExpeditionError("production resource readings differ from original")
        if instance.snapshot()!=snapshot:
            raise ExpeditionError("production watchdog state replay diverged")
        return instance

def simulate_production_health(world_digest:str,*,ticks:int=24)->dict:
    if type(ticks) is not int or not 1<=ticks<=240:
        raise ExpeditionError("production health simulation exceeds bounded quota")
    monitor=ProductionWatchdog(world_digest)
    for i in range(ticks):
        monitor.observe(ResourceSample(
            i+1,640+(i%5)*12,27.+(i%7),30_000-i*11,
            _digest({"world":world_digest,"tick":i+1}),
        ))
    return ProductionWatchdog.restore(world_digest,monitor.snapshot()).snapshot()
