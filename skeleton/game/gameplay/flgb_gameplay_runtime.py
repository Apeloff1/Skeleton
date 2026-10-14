"""FLGB-13 deterministic gameplay, scripting, narrative, and NPC AI contracts."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence
MAX_ID=256; MAX_ITEMS=100000; MAX_SCORE=1000000; MAX_VALUE=10**15
class GameplayContractError(ValueError): pass
def _int(v): return isinstance(v,int) and not isinstance(v,bool)
def req_id(v,n):
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID: raise GameplayContractError(f"invalid {n}")
    return v
def req_digest(v,n):
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise GameplayContractError(f"invalid {n}")
    return v
def dig(v):
    try: raw=json.dumps(v,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=False).encode()
    except (TypeError,ValueError) as exc: raise GameplayContractError("non-canonical value") from exc
    return sha256(raw).hexdigest()
@dataclass(frozen=True)
class GameplayAbility:
    ability_id:str; cooldown_ticks:int; cost:int; tags:tuple[str,...]; effect_digest:str
    def __post_init__(self):
        req_id(self.ability_id,"ability_id"); req_digest(self.effect_digest,"effect_digest")
        if not _int(self.cooldown_ticks) or self.cooldown_ticks<0 or not _int(self.cost) or self.cost<0: raise GameplayContractError("invalid ability budget")
        tags=tuple(sorted(self.tags));
        if len(set(tags))!=len(tags): raise GameplayContractError("duplicate ability tag")
        for t in tags: req_id(t,"tag")
        object.__setattr__(self,"tags",tags)
    @property
    def digest(self): return dig({"ability_id":self.ability_id,"cooldown_ticks":self.cooldown_ticks,"cost":self.cost,"tags":list(self.tags),"effect_digest":self.effect_digest})
@dataclass(frozen=True)
class ScriptSandboxPolicy:
    script_id:str; allowed_capabilities:tuple[str,...]; instruction_budget:int; memory_bytes:int
    def __post_init__(self):
        req_id(self.script_id,"script_id"); caps=tuple(sorted(self.allowed_capabilities))
        if len(set(caps))!=len(caps): raise GameplayContractError("duplicate capability")
        for c in caps: req_id(c,"capability")
        object.__setattr__(self,"allowed_capabilities",caps)
        if not _int(self.instruction_budget) or self.instruction_budget<1 or not _int(self.memory_bytes) or self.memory_bytes<1: raise GameplayContractError("invalid sandbox budget")
    def allows(self,capability:str)->bool: return req_id(capability,"capability") in self.allowed_capabilities
@dataclass(frozen=True)
class GameplayEvent:
    sequence:int; event_type:str; source_id:str; payload_digest:str
    def __post_init__(self):
        if not _int(self.sequence) or self.sequence<0: raise GameplayContractError("invalid event sequence")
        req_id(self.event_type,"event_type"); req_id(self.source_id,"source_id"); req_digest(self.payload_digest,"payload_digest")
class EventBus:
    def __init__(self,events:Sequence[GameplayEvent]=()):
        for i,e in enumerate(events):
            if e.sequence!=i: raise GameplayContractError("event sequence drift")
        self.events=tuple(events)
    def publish(self,event_type:str,source_id:str,payload_digest:str):
        return EventBus(self.events+(GameplayEvent(len(self.events),event_type,source_id,payload_digest),))
    @property
    def digest(self): return dig([e.__dict__ for e in self.events])
@dataclass(frozen=True)
class StateTransition:
    from_state:str; event:str; to_state:str
    def __post_init__(self): req_id(self.from_state,"from_state"); req_id(self.event,"event"); req_id(self.to_state,"to_state")
class StateMachine:
    def __init__(self,initial_state:str,transitions:Sequence[StateTransition]):
        self.initial_state=req_id(initial_state,"initial_state"); table={}
        for t in transitions:
            key=(t.from_state,t.event)
            if key in table: raise GameplayContractError("ambiguous state transition")
            table[key]=t.to_state
        self._table=MappingProxyType(table)
    def step(self,state:str,event:str)->str:
        key=(req_id(state,"state"),req_id(event,"event"))
        if key not in self._table: raise GameplayContractError("undefined state transition")
        return self._table[key]
@dataclass(frozen=True)
class QuestNode:
    node_id:str; dependencies:tuple[str,...]; completion_digest:str
    def __post_init__(self):
        req_id(self.node_id,"node_id"); req_digest(self.completion_digest,"completion_digest"); deps=tuple(sorted(self.dependencies))
        if self.node_id in deps or len(set(deps))!=len(deps): raise GameplayContractError("invalid quest dependencies")
        for d in deps: req_id(d,"dependency")
        object.__setattr__(self,"dependencies",deps)
def quest_order(nodes:Sequence[QuestNode])->tuple[str,...]:
    by={n.node_id:n for n in nodes}
    if len(by)!=len(nodes): raise GameplayContractError("duplicate quest node")
    remaining=set(by); done=[]
    while remaining:
        ready=sorted(n for n in remaining if set(by[n].dependencies).issubset(done))
        if not ready: raise GameplayContractError("quest graph cycle or missing dependency")
        done.extend(ready); remaining.difference_update(ready)
    return tuple(done)
@dataclass(frozen=True)
class DialogueChoice:
    choice_id:str; target_node_id:str; condition_digest:str|None=None
    def __post_init__(self):
        req_id(self.choice_id,"choice_id"); req_id(self.target_node_id,"target_node_id")
        if self.condition_digest is not None: req_digest(self.condition_digest,"condition_digest")
@dataclass(frozen=True)
class DialogueNode:
    node_id:str; text_digest:str; choices:tuple[DialogueChoice,...]
    def __post_init__(self):
        req_id(self.node_id,"node_id"); req_digest(self.text_digest,"text_digest")
        ids=[c.choice_id for c in self.choices]
        if len(set(ids))!=len(ids): raise GameplayContractError("duplicate dialogue choice")
def validate_dialogue(nodes:Sequence[DialogueNode])->None:
    ids={n.node_id for n in nodes}
    if len(ids)!=len(nodes): raise GameplayContractError("duplicate dialogue node")
    for n in nodes:
        for c in n.choices:
            if c.target_node_id not in ids: raise GameplayContractError("dialogue target missing")
@dataclass(frozen=True)
class CanonFact:
    fact_id:str; subject:str; predicate:str; object_digest:str; evidence_digest:str
    def __post_init__(self):
        req_id(self.fact_id,"fact_id"); req_id(self.subject,"subject"); req_id(self.predicate,"predicate"); req_digest(self.object_digest,"object_digest"); req_digest(self.evidence_digest,"evidence_digest")
class NarrativeCanon:
    def __init__(self,facts:Sequence[CanonFact]=()):
        by={f.fact_id:f for f in facts}
        if len(by)!=len(facts): raise GameplayContractError("duplicate canon fact")
        claims={}
        for f in facts:
            key=(f.subject,f.predicate)
            if key in claims and claims[key]!=f.object_digest: raise GameplayContractError("canon contradiction")
            claims[key]=f.object_digest
        self.facts=tuple(sorted(facts,key=lambda f:f.fact_id))
    @property
    def digest(self): return dig([f.__dict__ for f in self.facts])
@dataclass(frozen=True)
class NPCAction:
    action_id:str; preconditions:tuple[str,...]; effects:tuple[str,...]; cost:int
    def __post_init__(self):
        req_id(self.action_id,"action_id")
        for seq,name in ((self.preconditions,"precondition"),(self.effects,"effect")):
            if len(set(seq))!=len(seq): raise GameplayContractError(f"duplicate {name}")
            for x in seq: req_id(x,name)
        if not _int(self.cost) or self.cost<0: raise GameplayContractError("invalid action cost")
def plan_npc(actions:Sequence[NPCAction],facts:Sequence[str],goal:str)->tuple[str,...]:
    known=set(facts); req_id(goal,"goal"); chosen=[]; remaining={a.action_id:a for a in actions}
    if len(remaining)!=len(actions): raise GameplayContractError("duplicate NPC action")
    while goal not in known:
        ready=sorted((a for a in remaining.values() if set(a.preconditions).issubset(known)),key=lambda a:(a.cost,a.action_id))
        if not ready: raise GameplayContractError("NPC goal unreachable")
        action=ready[0]; chosen.append(action.action_id); known.update(action.effects); del remaining[action.action_id]
    return tuple(chosen)
@dataclass(frozen=True)
class BehaviorNode:
    node_id:str; kind:str; children:tuple[str,...]=()
    def __post_init__(self):
        req_id(self.node_id,"node_id")
        if self.kind not in {"sequence","selector","condition","action"}: raise GameplayContractError("invalid behavior kind")
        if len(set(self.children))!=len(self.children): raise GameplayContractError("duplicate behavior child")
        for c in self.children: req_id(c,"child")
def validate_behavior_tree(nodes:Sequence[BehaviorNode],root_id:str)->None:
    by={n.node_id:n for n in nodes}; root_id=req_id(root_id,"root_id")
    if len(by)!=len(nodes) or root_id not in by: raise GameplayContractError("invalid behavior tree root")
    seen=set(); active=set()
    def visit(nid):
        if nid in active: raise GameplayContractError("behavior tree cycle")
        if nid in seen: return
        if nid not in by: raise GameplayContractError("missing behavior child")
        active.add(nid)
        for c in by[nid].children: visit(c)
        active.remove(nid); seen.add(nid)
    visit(root_id)
@dataclass(frozen=True)
class CombatRule:
    rule_id:str; priority:int; condition_digest:str; effect_digest:str
    def __post_init__(self):
        req_id(self.rule_id,"rule_id"); req_digest(self.condition_digest,"condition_digest"); req_digest(self.effect_digest,"effect_digest")
        if not _int(self.priority): raise GameplayContractError("invalid combat priority")
def order_combat_rules(rules:Sequence[CombatRule])->tuple[CombatRule,...]:
    ids=[r.rule_id for r in rules]
    if len(set(ids))!=len(ids): raise GameplayContractError("duplicate combat rule")
    return tuple(sorted(rules,key=lambda r:(-r.priority,r.rule_id)))
@dataclass(frozen=True)
class EconomyRule:
    currency_id:str; min_balance:int; max_balance:int; transfer_limit:int
    def __post_init__(self):
        req_id(self.currency_id,"currency_id")
        for name in ("min_balance","max_balance","transfer_limit"):
            if not _int(getattr(self,name)): raise GameplayContractError(f"invalid {name}")
        if self.min_balance<0 or self.max_balance<self.min_balance or self.transfer_limit<0: raise GameplayContractError("invalid economy bounds")
    def transfer(self,source:int,target:int,amount:int)->tuple[int,int]:
        if not all(_int(v) for v in (source,target,amount)) or amount<0 or amount>self.transfer_limit: raise GameplayContractError("invalid transfer")
        if source-amount<self.min_balance or target+amount>self.max_balance: raise GameplayContractError("transfer violates economy bounds")
        return source-amount,target+amount
@dataclass(frozen=True)
class SaveableGameplayState:
    world_id:str; schema_version:int; tick:int; state_digest:str; canon_digest:str; parent_save_digest:str|None=None
    def __post_init__(self):
        req_id(self.world_id,"world_id"); req_digest(self.state_digest,"state_digest"); req_digest(self.canon_digest,"canon_digest")
        if not _int(self.schema_version) or self.schema_version<1 or not _int(self.tick) or self.tick<0: raise GameplayContractError("invalid save metadata")
        if self.parent_save_digest is not None: req_digest(self.parent_save_digest,"parent_save_digest")
    @property
    def digest(self): return dig(self.__dict__)
