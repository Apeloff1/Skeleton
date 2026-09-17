"""Deterministic ECS runtime, checkpoints and replay evidence."""
from __future__ import annotations
import copy
from dataclasses import dataclass
from typing import Any,Callable,Mapping
from .canonical import chained_digest,digest
from .errors import ReplayDivergenceError,ReplayError,ScheduleError,ValidationError
from .execution import CommandBuffer,Event,EventQueue,SimulationClock,SnapshotHistory,capture_snapshot,restore_snapshot
from .schedule import ExecutionPlan,SystemGraph,SystemSpec
from .store import EntityStore
SystemHandler=Callable[["SystemContext"],None]
@dataclass
class SystemContext:
    store:EntityStore;commands:CommandBuffer;events:EventQueue;clock:SimulationClock;system:SystemSpec
    def emit(self,event_type,payload):return self.events.publish(event_type,payload,tick=self.clock.tick,source=self.system.system_id)
@dataclass(frozen=True)
class SystemExecutionReceipt:system_id:str;before_digest:str;after_digest:str;command_count:int;event_count:int
@dataclass(frozen=True)
class TickReceipt:tick:int;before_digest:str;after_digest:str;plan_fingerprint:str;systems:tuple[SystemExecutionReceipt,...];emitted_events:int
@dataclass(frozen=True)
class RuntimeMetrics:ticks:int;system_executions:int;emitted_events:int;last_state_digest:str
@dataclass(frozen=True)
class RuntimeCheckpoint:store:Any;clock:Any;events:Mapping[str,Any];checkpoint_digest:str
def capture_checkpoint(runtime):
    store=capture_snapshot(runtime.store);clock=runtime.clock.snapshot();events=runtime.events.snapshot();material={"store":store.state_digest,"clock":clock.__dict__,"events":events};return RuntimeCheckpoint(store,clock,copy.deepcopy(events),digest(material))
def restore_checkpoint(runtime,checkpoint):
    expected=digest({"store":checkpoint.store.state_digest,"clock":checkpoint.clock.__dict__,"events":checkpoint.events})
    if expected!=checkpoint.checkpoint_digest:raise ReplayError("checkpoint digest mismatch")
    restore_snapshot(runtime.store,checkpoint.store);runtime.clock.restore(checkpoint.clock);runtime.events.restore(checkpoint.events)
def checkpoint_matches_runtime(runtime,checkpoint):return runtime.store.state_digest==checkpoint.store.state_digest and runtime.clock.snapshot()==checkpoint.clock and runtime.events.snapshot()==checkpoint.events
class SimulationRuntime:
    def __init__(self,store=None,graph=None,*,clock=None,history_capacity=128):
        self.store=store or EntityStore();self.graph=graph or SystemGraph();self.clock=clock or SimulationClock();self.events=EventQueue();self.history=SnapshotHistory(history_capacity);self._handlers={};self._ticks=0;self._system_executions=0;self._emitted_events=0
    def bind(self,system_id,handler):
        self.graph.get(system_id)
        if not callable(handler):raise ValidationError("system handler must be callable")
        self._handlers[system_id]=handler
    def register(self,spec,handler=None):
        registered=self.graph.register(spec)
        if handler is not None:self.bind(spec.system_id,handler)
        return registered
    def plan(self):return self.graph.plan()
    def step(self):
        plan=self.plan();before=self.store.state_digest;self.history.append(capture_snapshot(self.store));system_receipts=[];events_before=len(self.events.pending());self.clock.step(1);self.store.advance_tick(self.clock.tick)
        for batch in plan.batches:
            for sid in batch.system_ids:
                if sid not in self._handlers:raise ScheduleError("system handler missing",context={"system_id":sid})
                spec=self.graph.get(sid);commands=CommandBuffer();state_before=self.store.state_digest;event_count_before=len(self.events.pending());ctx=SystemContext(self.store,commands,self.events,self.clock,spec)
                try:self._handlers[sid](ctx);command_count=len(commands);commands.commit(self.store)
                except Exception:restore_snapshot(self.store,self.history.latest());raise
                emitted=len(self.events.pending())-event_count_before;system_receipts.append(SystemExecutionReceipt(sid,state_before,self.store.state_digest,command_count,emitted));self._system_executions+=1
        self.store.assert_invariants();self._ticks+=1;emitted_total=len(self.events.pending())-events_before;self._emitted_events+=emitted_total;return TickReceipt(self.clock.tick,before,self.store.state_digest,plan.fingerprint,tuple(system_receipts),emitted_total)
    def rollback_to_revision(self,revision):snapshot=self.history.at_revision(revision);restore_snapshot(self.store,snapshot);return snapshot
    def metrics(self):return RuntimeMetrics(self._ticks,self._system_executions,self._emitted_events,self.store.state_digest)
@dataclass(frozen=True)
class ReplayFrame:index:int;tick:int;before_digest:str;after_digest:str;plan_fingerprint:str;receipt_digest:str
@dataclass(frozen=True)
class ReplayTape:initial:RuntimeCheckpoint;frames:tuple[ReplayFrame,...];chain_digest:str
@dataclass(frozen=True)
class ReplayVerification:frames:int;final_digest:str;chain_digest:str;ok:bool
class ReplayRecorder:
    def __init__(self,runtime):self.runtime=runtime;self.initial=capture_checkpoint(runtime);self.frames=[];self._chain="0"*64
    def step(self):
        receipt=self.runtime.step();frame=ReplayFrame(len(self.frames),receipt.tick,receipt.before_digest,receipt.after_digest,receipt.plan_fingerprint,digest(receipt.__dict__));self._chain=chained_digest(self._chain,frame.__dict__);self.frames.append(frame);return receipt
    def tape(self):return ReplayTape(self.initial,tuple(self.frames),self._chain)
def replay(runtime_factory,tape):
    runtime=runtime_factory();restore_checkpoint(runtime,tape.initial);chain="0"*64
    for expected in tape.frames:
        receipt=runtime.step();actual=ReplayFrame(expected.index,receipt.tick,receipt.before_digest,receipt.after_digest,receipt.plan_fingerprint,digest(receipt.__dict__))
        if actual!=expected:raise ReplayDivergenceError("replay frame diverged",context={"frame":expected.index})
        chain=chained_digest(chain,actual.__dict__)
    if chain!=tape.chain_digest:raise ReplayDivergenceError("replay chain digest mismatch")
    return ReplayVerification(len(tape.frames),runtime.store.state_digest,chain,True)
