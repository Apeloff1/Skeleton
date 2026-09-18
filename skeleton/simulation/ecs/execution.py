"""Mutation buffering, events, deterministic clocking, snapshots and deltas."""
from __future__ import annotations
import copy
from dataclasses import dataclass
from enum import Enum
from typing import Any,Iterable,Mapping
from .errors import ClockError,CommandError,CommandOverflowError,DeltaError,EventError,EventOverflowError,SnapshotDigestError,SnapshotError,SnapshotVersionError,TransactionError
from .schedule import ExecutionBatch,ExecutionPlan,SystemGraph,SystemPhase,SystemSpec,conflicts
from .store import EntityStore
MAX_COMMANDS=100_000;MAX_EVENTS=100_000;MAX_HISTORY=1024;SNAPSHOT_SCHEMA="simulation.store_snapshot.v1"
class CommandKind(str,Enum):CREATE_ENTITY="create_entity";DELETE_ENTITY="delete_entity";SET_COMPONENT="set_component";PATCH_COMPONENT="patch_component";REMOVE_COMPONENT="remove_component";SET_RESOURCE="set_resource";REMOVE_RESOURCE="remove_resource"
@dataclass(frozen=True)
class Command:
    kind:CommandKind;payload:Mapping[str,Any];sequence:int=0;source:str=""
    def __post_init__(self):
        if not isinstance(self.kind,CommandKind):object.__setattr__(self,"kind",CommandKind(self.kind))
        if isinstance(self.sequence,bool) or not isinstance(self.sequence,int) or self.sequence<0:raise CommandError("command sequence must be non-negative int")
        if not isinstance(self.payload,Mapping):raise CommandError("command payload must be mapping")
@dataclass(frozen=True)
class CommandResult:sequence:int;kind:str;ok:bool;revision:int;result:Any=None
@dataclass(frozen=True)
class CommitReceipt:before_digest:str;after_digest:str;before_revision:int;after_revision:int;results:tuple[CommandResult,...]
class CommandBuffer:
    def __init__(self,max_commands:int=MAX_COMMANDS):
        if isinstance(max_commands,bool) or not isinstance(max_commands,int) or not 1<=max_commands<=MAX_COMMANDS:raise CommandError("invalid command bound")
        self.max_commands=max_commands;self._commands=[];self._sequence=0
    def __len__(self):return len(self._commands)
    def add(self,kind,payload,*,source=""):
        if len(self._commands)>=self.max_commands:raise CommandOverflowError("command buffer full")
        cmd=Command(CommandKind(kind),copy.deepcopy(dict(payload)),self._sequence,source);self._sequence+=1;self._commands.append(cmd);return cmd
    def commands(self):return tuple(self._commands)
    def clear(self):self._commands.clear()
    def commit(self,store:EntityStore):
        before_digest=store.state_digest;before_revision=store.revision;results=[]
        try:
            with store.transaction():
                for cmd in self._commands:
                    p=dict(cmd.payload);result=None
                    if cmd.kind is CommandKind.CREATE_ENTITY:result=store.create_entity(p.get("entity_id"),hint=p.get("hint")).entity_id
                    elif cmd.kind is CommandKind.DELETE_ENTITY:result=store.delete_entity(p["entity_id"]).to_record()
                    elif cmd.kind is CommandKind.SET_COMPONENT:result=store.set_component(p["entity_id"],p["schema_id"],p["data"],version=p.get("version"),replace=p.get("replace",True)).to_record()
                    elif cmd.kind is CommandKind.PATCH_COMPONENT:result=store.patch_component(p["entity_id"],p["schema_id"],p["patch"]).to_record()
                    elif cmd.kind is CommandKind.REMOVE_COMPONENT:result=store.remove_component(p["entity_id"],p["schema_id"]).to_record()
                    elif cmd.kind is CommandKind.SET_RESOURCE:result=store.set_resource(p["resource_id"],p["value"]).to_record()
                    elif cmd.kind is CommandKind.REMOVE_RESOURCE:result=store.remove_resource(p["resource_id"]).to_record()
                    else:raise CommandError("unsupported command kind")
                    results.append(CommandResult(cmd.sequence,cmd.kind.value,True,store.revision,copy.deepcopy(result)))
                store.assert_invariants()
        except Exception as exc:raise TransactionError("command buffer commit failed",context={"commands":len(self._commands),"error_type":type(exc).__name__}) from exc
        self.clear();return CommitReceipt(before_digest,store.state_digest,before_revision,store.revision,tuple(results))
@dataclass(frozen=True)
class Event:
    event_type:str;payload:Any;tick:int;sequence:int;source:str=""
    @property
    def fingerprint(self):
        from .canonical import digest
        return digest({"type":self.event_type,"payload":self.payload,"tick":self.tick,"sequence":self.sequence,"source":self.source})
@dataclass(frozen=True)
class EventReceipt:published:int;delivered:int;remaining:int;digest:str
class EventQueue:
    def __init__(self,max_events:int=MAX_EVENTS):self.max_events=max_events;self._events=[];self._sequence=0
    def publish(self,event_type,payload,*,tick,source=""):
        if not event_type:raise EventError("event type required")
        if len(self._events)>=self.max_events:raise EventOverflowError("event queue full")
        ev=Event(event_type,copy.deepcopy(payload),tick,self._sequence,source);self._sequence+=1;self._events.append(ev);return ev
    def pending(self):return tuple(sorted(self._events,key=lambda e:(e.tick,e.sequence,e.event_type)))
    def drain(self,*,through_tick=None):
        ready=[];future=[]
        for ev in self.pending():
            (ready if through_tick is None or ev.tick<=through_tick else future).append(ev)
        self._events=future;return tuple(ready)
    def snapshot(self):return {"sequence":self._sequence,"events":[e.__dict__ for e in self.pending()]}
    def restore(self,record):self._events=[Event(**row) for row in record["events"]];self._sequence=int(record["sequence"])
@dataclass(frozen=True)
class ClockSnapshot:tick:int;elapsed_ns:int;step_ns:int;paused:bool
class SimulationClock:
    def __init__(self,*,step_ns=16_666_667,tick=0,elapsed_ns=0,paused=False):
        for name,value,minimum in (("step_ns",step_ns,1),("tick",tick,0),("elapsed_ns",elapsed_ns,0)):
            if isinstance(value,bool) or not isinstance(value,int) or value<minimum:raise ClockError(f"invalid {name}")
        self.step_ns=step_ns;self.tick=tick;self.elapsed_ns=elapsed_ns;self.paused=bool(paused)
    def step(self,count=1):
        if isinstance(count,bool) or not isinstance(count,int) or count<0:raise ClockError("step count invalid")
        if self.paused and count:raise ClockError("clock is paused")
        self.tick+=count;self.elapsed_ns+=self.step_ns*count;return self.snapshot()
    def pause(self):self.paused=True
    def resume(self):self.paused=False
    def snapshot(self):return ClockSnapshot(self.tick,self.elapsed_ns,self.step_ns,self.paused)
    def restore(self,snapshot):self.tick=snapshot.tick;self.elapsed_ns=snapshot.elapsed_ns;self.step_ns=snapshot.step_ns;self.paused=snapshot.paused
@dataclass(frozen=True)
class StoreSnapshot:
    schema:str;store:EntityStore;state_digest:str;revision:int;tick:int
    def clone_store(self):return self.store.clone()
def capture_snapshot(store):
    cloned=store.clone();return StoreSnapshot(SNAPSHOT_SCHEMA,cloned,cloned.state_digest,cloned.revision,cloned.tick)
def restore_snapshot(store,snapshot):
    if snapshot.schema!=SNAPSHOT_SCHEMA:raise SnapshotVersionError("unsupported snapshot schema")
    if snapshot.store.state_digest!=snapshot.state_digest:raise SnapshotDigestError("snapshot store digest mismatch")
    store.replace_from(snapshot.store)
class SnapshotHistory:
    def __init__(self,capacity=128):
        if not 1<=capacity<=MAX_HISTORY:raise SnapshotError("invalid snapshot history capacity")
        self.capacity=capacity;self._items=[]
    def append(self,snapshot):self._items.append(copy.deepcopy(snapshot));self._items=self._items[-self.capacity:]
    def latest(self):
        if not self._items:raise SnapshotError("snapshot history empty")
        return copy.deepcopy(self._items[-1])
    def at_revision(self,revision):
        for item in reversed(self._items):
            if item.revision==revision:return copy.deepcopy(item)
        raise SnapshotError("snapshot revision not retained",context={"revision":revision})
    def __len__(self):return len(self._items)
@dataclass(frozen=True)
class DeltaOperation:op:str;path:tuple[str,...];value:Any=None
@dataclass(frozen=True)
class StoreDelta:base_digest:str;target_digest:str;base_revision:int;target_revision:int;operations:tuple[DeltaOperation,...]
def diff_snapshots(base,target):
    if base.state_digest==target.state_digest:return StoreDelta(base.state_digest,target.state_digest,base.revision,target.revision,())
    return StoreDelta(base.state_digest,target.state_digest,base.revision,target.revision,(DeltaOperation("replace_store",(),target.clone_store()),))
def apply_delta(store,delta):
    if store.state_digest!=delta.base_digest:raise DeltaError("delta base digest mismatch")
    for op in delta.operations:
        if op.op!="replace_store" or not isinstance(op.value,EntityStore):raise DeltaError("unsupported delta operation")
        store.replace_from(op.value)
    if store.state_digest!=delta.target_digest:raise DeltaError("delta target digest mismatch")
