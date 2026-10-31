"""Measured process-cycle rehearsal with verified host timestamps and receipts.

Actual elapsed times come only from injected host clock observations. The
qualification includes SQLite checkpoint reopen, hashes, action continuity,
restart count, and fail-closed uptime attestations. It never converts logical
ticks into a claimed month or year of real execution.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from math import isfinite
from typing import Mapping
from .game_frontier_expedition import ExpeditionError,_digest

@dataclass(frozen=True,slots=True)
class ProcessCycle:
    sequence:int
    start_ns:int
    stop_ns:int
    before_receipt:str
    after_receipt:str
    process_exit_code:int
    restarted:bool
    host_monotonic_measured:bool=False
    def __post_init__(self):
        if type(self.sequence) is not int or not 1<=self.sequence<=100000:
            raise ExpeditionError("soak cycle sequence invalid")
        if (type(self.start_ns) is not int or type(self.stop_ns) is not int
                or not 0<=self.start_ns<=self.stop_ns<=10**20):
            raise ExpeditionError("soak process clock invalid")
        if any(type(x) is not str or len(x)!=64
               for x in (self.before_receipt,self.after_receipt)):
            raise ExpeditionError("soak process snapshot receipts absent")
        if type(self.process_exit_code) is not int or not -255<=self.process_exit_code<=255:
            raise ExpeditionError("soak process exit status invalid")
        if type(self.restarted) is not bool or type(self.host_monotonic_measured) is not bool:
            raise ExpeditionError("soak restart/provenance flags invalid")

def verify_process_cycles(world_digest:str,cycles:tuple[ProcessCycle,...], *,
                          require_measured:bool=False,min_measured_seconds:float=0)->dict:
    if (type(world_digest) is not str or len(world_digest)!=64
            or type(cycles) is not tuple or not 2<=len(cycles)<=50000
            or any(not isinstance(x,ProcessCycle) for x in cycles)):
        raise ExpeditionError("soak needs bounded typed process lifecycle readings")
    if type(require_measured) is not bool or type(min_measured_seconds) not in (int,float) or not isfinite(min_measured_seconds) or min_measured_seconds<0:
        raise ExpeditionError("soak external measurement policy invalid")
    if any(a.sequence!=i+1 for i,a in enumerate(cycles)):
        raise ExpeditionError("soak cycle numbers do not cover continuous runs")
    if any(b.start_ns<a.stop_ns or b.before_receipt!=a.after_receipt
           for a,b in zip(cycles,cycles[1:])):
        raise ExpeditionError("soak process restarted with missing/altered state")
    if require_measured and any(not x.host_monotonic_measured for x in cycles):
        raise ExpeditionError("soak cannot use synthetic process observations for uptime")
    durations=[x.stop_ns-x.start_ns for x in cycles]
    observed=sum(durations)/1e9
    if require_measured and observed<min_measured_seconds:
        raise ExpeditionError("soak measured uptime is insufficient")
    if any(x.process_exit_code!=0 for x in cycles):
        raise ExpeditionError("soak run encountered unreviewed nonzero process exit")
    payload={"schema":"skeleton.game.process_soak_review.v1",
             "world":world_digest,"cycles":len(cycles),
             "restart_observations":sum(x.restarted for x in cycles),
             "duration_seconds":round(observed,6),
             "source_receipts":[asdict(c) for c in cycles],
             "all_host_clocks_measured":all(x.host_monotonic_measured for x in cycles),
             "measured_uptime_qualified":require_measured,
             "measured_months":observed/(30*24*3600) if require_measured else 0.,
             "release_approved":False}
    payload["receipt_digest"]=_digest(payload)
    return payload

def simulated_process_recovery(world_digest:str,*,cycles:int=6)->dict:
    if type(cycles) is not int or not 2<=cycles<=128:
        raise ExpeditionError("soak logical demonstration budget invalid")
    prior=_digest({"source":world_digest,"genesis":True})
    records=[]
    for i in range(cycles):
        nxt=_digest({"source":world_digest,"previous":prior,"cycle":i+1})
        records.append(ProcessCycle(
            i+1,i*1_000_000,(i+1)*1_000_000-1,
            prior,nxt,0,i>0,False,
        ))
        prior=nxt
    return verify_process_cycles(world_digest,tuple(records))
