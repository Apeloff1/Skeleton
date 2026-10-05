"""Distributed training topology and collective state for VOL-144."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import re
_ID=re.compile(r"^[A-Z][A-Z0-9_.:-]{2,127}$")
class DistributedTrainingError(ValueError):pass
class WorkerState(str,Enum): ACTIVE="active"; LOST="lost"; FENCED="fenced"
def _id(v,f):
 if not isinstance(v,str) or not _ID.fullmatch(v):raise DistributedTrainingError(f"{f} must be stable identifier")
 return v
@dataclass(frozen=True,slots=True)
class TrainingWorker:
 worker_id:str;rank:int;epoch:int;state:WorkerState=WorkerState.ACTIVE
 def __post_init__(self):
  object.__setattr__(self,"worker_id",_id(self.worker_id,"worker_id"))
  if self.rank<0 or self.epoch<1:raise DistributedTrainingError("invalid worker rank/epoch")
@dataclass(frozen=True,slots=True)
class TrainingTopology:
 topology_id:str;workers:tuple[TrainingWorker,...];collective_timeout_ticks:int
 def __post_init__(self):
  object.__setattr__(self,"topology_id",_id(self.topology_id,"topology_id"))
  if self.collective_timeout_ticks<1 or not self.workers:raise DistributedTrainingError("bounded collective topology required")
  ranks=[w.rank for w in self.workers]
  if len(set(ranks))!=len(ranks) or sorted(ranks)!=list(range(len(ranks))):raise DistributedTrainingError("ranks must be unique and contiguous")
  if len({w.epoch for w in self.workers})!=1:raise DistributedTrainingError("mixed worker epochs")
@dataclass(frozen=True,slots=True)
class CollectiveState:
 collective_id:str;topology_id:str;epoch:int;started_tick:int;completed_ranks:frozenset[int]
 def __post_init__(self):
  object.__setattr__(self,"collective_id",_id(self.collective_id,"collective_id"));object.__setattr__(self,"topology_id",_id(self.topology_id,"topology_id"))
class CollectiveCoordinator:
 def __init__(self,topology):self.topology=topology
 def evaluate(self,state,current_tick):
  if state.topology_id!=self.topology.topology_id or state.epoch!=self.topology.workers[0].epoch:raise DistributedTrainingError("stale collective")
  expected=set(range(len(self.topology.workers)))
  if not set(state.completed_ranks)<=expected:raise DistributedTrainingError("unknown collective rank")
  if set(state.completed_ranks)==expected:return "complete"
  if current_tick-state.started_tick>=self.topology.collective_timeout_ticks:return "timeout"
  return "waiting"
