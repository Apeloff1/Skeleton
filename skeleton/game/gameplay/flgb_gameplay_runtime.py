"""FLGB-13 deterministic gameplay, narrative, NPC, combat, economy, and save contracts."""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

MAX_ID_CHARS=256
MAX_TAGS=1024
MAX_EVENTS=1_000_000
MAX_STATES=100_000
MAX_GRAPH_NODES=100_000
MAX_CHOICES=4096
MAX_GOALS=10_000
MAX_BEHAVIOR_NODES=100_000
MAX_VALUE=10**15
MAX_SCORE_PPM=1_000_000

class GameplayContractError(ValueError):
    """Fail-closed FLGB-13 contract error."""

def _is_int(v:Any)->bool:return isinstance(v,int) and not isinstance(v,bool)
def require_id(v:str,name:str)->str:
    if not isinstance(v,str) or not v or v!=v.strip() or len(v)>MAX_ID_CHARS or any(ord(c)<32 for c in v): raise GameplayContractError(f"invalid {name}")
    return v
def require_digest(v:str,name:str)->str:
    if not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v): raise GameplayContractError(f"invalid {name}")
    return v
def digest_json(v:Any)->str:
    try:raw=json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode("utf-8")
    except (TypeError,ValueError) as exc: raise GameplayContractError("value is not canonical-json encodable") from exc
    return sha256(raw).hexdigest()
def canonical_ids(values:Sequence[str],name:str)->tuple[str,...]:
    out=tuple(sorted(values))
    if len(out)>MAX_TAGS or len(set(out))!=len(out): raise GameplayContractError(f"invalid {name}")
    for item in out: require_id(item,name)
    return out

@dataclass(frozen=True)
class GameplayAbility:
    ability_id:str
    cost_units:int
    cooldown_ticks:int
    tags:tuple[str,...]=()
    requirement_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.ability_id,"ability_id")
        if not _is_int(self.cost_units) or not 0<=self.cost_units<=MAX_VALUE: raise GameplayContractError("invalid ability cost")
        if not _is_int(self.cooldown_ticks) or self.cooldown_ticks<0: raise GameplayContractError("invalid cooldown")
        object.__setattr__(self,"tags",canonical_ids(self.tags,"ability tag"))
        if self.requirement_digest is not None: require_digest(self.requirement_digest,"requirement_digest")

    def can_activate(self,resource_units:int,last_used_tick:int|None,current_tick:int)->bool:
        if not _is_int(resource_units) or resource_units<0 or not _is_int(current_tick) or current_tick<0: raise GameplayContractError("invalid activation counters")
        if last_used_tick is not None and (not _is_int(last_used_tick) or last_used_tick<0 or last_used_tick>current_tick): raise GameplayContractError("invalid last_used_tick")
        cooled=last_used_tick is None or current_tick-last_used_tick>=self.cooldown_ticks
        return resource_units>=self.cost_units and cooled

@dataclass(frozen=True)
class ScriptSandboxPolicy:
    policy_id:str
    allowed_apis:tuple[str,...]
    max_instructions:int
    max_memory_bytes:int
    allow_network:bool=False
    allow_process_spawn:bool=False

    def __post_init__(self)->None:
        require_id(self.policy_id,"policy_id")
        object.__setattr__(self,"allowed_apis",canonical_ids(self.allowed_apis,"allowed api"))
        if not _is_int(self.max_instructions) or self.max_instructions<=0: raise GameplayContractError("invalid max_instructions")
        if not _is_int(self.max_memory_bytes) or self.max_memory_bytes<=0: raise GameplayContractError("invalid max_memory_bytes")
        if not isinstance(self.allow_network,bool) or not isinstance(self.allow_process_spawn,bool): raise GameplayContractError("sandbox flags must be boolean")

    def authorizes(self,api:str)->bool:return require_id(api,"api") in self.allowed_apis

@dataclass(frozen=True)
class GameplayEvent:
    sequence:int
    topic:str
    source_id:str
    payload_digest:str
    prior_event_digest:str|None=None

    def __post_init__(self)->None:
        if not _is_int(self.sequence) or self.sequence<0: raise GameplayContractError("invalid event sequence")
        require_id(self.topic,"topic"); require_id(self.source_id,"source_id"); require_digest(self.payload_digest,"payload_digest")
        if self.prior_event_digest is not None: require_digest(self.prior_event_digest,"prior_event_digest")
        if self.sequence==0 and self.prior_event_digest is not None: raise GameplayContractError("genesis event cannot have parent")
        if self.sequence>0 and self.prior_event_digest is None: raise GameplayContractError("non-genesis event requires parent")
    @property
    def digest(self)->str:return digest_json(self.__dict__)

class GameplayEventBus:
    def __init__(self,events:Sequence[GameplayEvent]=())->None:
        if len(events)>MAX_EVENTS: raise GameplayContractError("event budget exceeded")
        for i,event in enumerate(events):
            if event.sequence!=i: raise GameplayContractError("event sequence drift")
            expected=events[i-1].digest if i else None
            if event.prior_event_digest!=expected: raise GameplayContractError("event chain drift")
        self.events=tuple(events)
    def publish(self,topic:str,source_id:str,payload_digest:str)->"GameplayEventBus":
        prior=self.events[-1].digest if self.events else None
        event=GameplayEvent(len(self.events),topic,source_id,require_digest(payload_digest,"payload_digest"),prior)
        return GameplayEventBus(self.events+(event,))
    def topic(self,topic:str)->tuple[GameplayEvent,...]:
        topic=require_id(topic,"topic"); return tuple(e for e in self.events if e.topic==topic)

@dataclass(frozen=True)
class StateTransition:
    transition_id:str
    source:str
    target:str
    guard_digest:str|None=None

    def __post_init__(self)->None:
        require_id(self.transition_id,"transition_id"); require_id(self.source,"source"); require_id(self.target,"target")
        if self.source==self.target: raise GameplayContractError("self state transition forbidden")
        if self.guard_digest is not None: require_digest(self.guard_digest,"guard_digest")

class StateMachine:
    def __init__(self,states:Sequence[str],transitions:Sequence[StateTransition],initial_state:str)->None:
        state_ids=canonical_ids(states,"state")
        if not state_ids or len(state_ids)>MAX_STATES: raise GameplayContractError("state count out of bounds")
        initial_state=require_id(initial_state,"initial_state")
        if initial_state not in state_ids: raise GameplayContractError("unknown initial state")
        ids=[t.transition_id for t in transitions]
        if len(set(ids))!=len(ids): raise GameplayContractError("duplicate transition")
        for t in transitions:
            if t.source not in state_ids or t.target not in state_ids: raise GameplayContractError("transition references unknown state")
        self.states=state_ids; self.transitions=tuple(sorted(transitions,key=lambda t:t.transition_id)); self.initial_state=initial_state
    def next_states(self,state:str)->tuple[str,...]:
        state=require_id(state,"state")
        if state not in self.states: raise GameplayContractError("unknown state")
        return tuple(sorted(t.target for t in self.transitions if t.source==state))

@dataclass(frozen=True)
class QuestNode:
    quest_id:str
    dependencies:tuple[str,...]
    completion_digest:str

    def __post_init__(self)->None:
        require_id(self.quest_id,"quest_id"); require_digest(self.completion_digest,"completion_digest")
        deps=canonical_ids(self.dependencies,"quest dependency")
        if self.quest_id in deps: raise GameplayContractError("quest cannot depend on itself")
        object.__setattr__(self,"dependencies",deps)

class QuestGraph:
    def __init__(self,nodes:Sequence[QuestNode])->None:
        if not nodes or len(nodes)>MAX_GRAPH_NODES: raise GameplayContractError("quest node count out of bounds")
        by_id={n.quest_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise GameplayContractError("duplicate quest node")
        for node in nodes:
            if set(node.dependencies)-set(by_id): raise GameplayContractError("unknown quest dependency")
        self._nodes=MappingProxyType(by_id); self._order=self._topological()
    def _topological(self)->tuple[str,...]:
        remaining=set(self._nodes); done=set(); out=[]
        while remaining:
            ready=sorted(q for q in remaining if set(self._nodes[q].dependencies).issubset(done))
            if not ready: raise GameplayContractError("quest graph cycle")
            out.extend(ready); done.update(ready); remaining.difference_update(ready)
        return tuple(out)
    @property
    def order(self)->tuple[str,...]:return self._order

@dataclass(frozen=True)
class DialogueChoice:
    choice_id:str
    target_node:str
    condition_digest:str|None=None
    def __post_init__(self)->None:
        require_id(self.choice_id,"choice_id"); require_id(self.target_node,"target_node")
        if self.condition_digest is not None: require_digest(self.condition_digest,"condition_digest")
@dataclass(frozen=True)
class DialogueNode:
    node_id:str
    line_digest:str
    choices:tuple[DialogueChoice,...]=()
    def __post_init__(self)->None:
        require_id(self.node_id,"node_id"); require_digest(self.line_digest,"line_digest")
        if len(self.choices)>MAX_CHOICES: raise GameplayContractError("dialogue choice budget exceeded")
        ids=[c.choice_id for c in self.choices]
        if len(set(ids))!=len(ids): raise GameplayContractError("duplicate dialogue choice")
class DialogueGraph:
    def __init__(self,nodes:Sequence[DialogueNode],entry_node:str)->None:
        if not nodes or len(nodes)>MAX_GRAPH_NODES: raise GameplayContractError("dialogue node count out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise GameplayContractError("duplicate dialogue node")
        entry_node=require_id(entry_node,"entry_node")
        if entry_node not in by_id: raise GameplayContractError("unknown dialogue entry")
        for node in nodes:
            for choice in node.choices:
                if choice.target_node not in by_id: raise GameplayContractError("dialogue choice targets unknown node")
        self._nodes=MappingProxyType(by_id); self.entry_node=entry_node
    @property
    def digest(self)->str:return digest_json({"entry_node":self.entry_node,"nodes":[{"node_id":n.node_id,"line_digest":n.line_digest,"choices":[c.__dict__ for c in n.choices]} for n in sorted(self._nodes.values(),key=lambda n:n.node_id)]})

@dataclass(frozen=True)
class CanonFact:
    fact_id:str
    statement_digest:str
    evidence_digest:str
    revision:int=0
    parent_digest:str|None=None
    def __post_init__(self)->None:
        require_id(self.fact_id,"fact_id"); require_digest(self.statement_digest,"statement_digest"); require_digest(self.evidence_digest,"evidence_digest")
        if not _is_int(self.revision) or self.revision<0: raise GameplayContractError("invalid canon revision")
        if self.parent_digest is not None: require_digest(self.parent_digest,"parent_digest")
        if self.revision==0 and self.parent_digest is not None: raise GameplayContractError("genesis canon fact cannot have parent")
        if self.revision>0 and self.parent_digest is None: raise GameplayContractError("canon revision requires parent")
    @property
    def digest(self)->str:return digest_json(self.__dict__)
    def revise(self,statement_digest:str,evidence_digest:str)->"CanonFact":return CanonFact(self.fact_id,require_digest(statement_digest,"statement_digest"),require_digest(evidence_digest,"evidence_digest"),self.revision+1,self.digest)

@dataclass(frozen=True)
class NPCGoal:
    goal_id:str
    utility_ppm:int
    risk_ppm:int
    action_digest:str
    def __post_init__(self)->None:
        require_id(self.goal_id,"goal_id"); require_digest(self.action_digest,"action_digest")
        for name in ("utility_ppm","risk_ppm"):
            v=getattr(self,name)
            if not _is_int(v) or not 0<=v<=MAX_SCORE_PPM: raise GameplayContractError(f"invalid {name}")
def plan_npc(goals:Sequence[NPCGoal],maximum_risk_ppm:int)->tuple[NPCGoal,...]:
    if len(goals)>MAX_GOALS: raise GameplayContractError("NPC goal budget exceeded")
    if not _is_int(maximum_risk_ppm) or not 0<=maximum_risk_ppm<=MAX_SCORE_PPM: raise GameplayContractError("invalid risk gate")
    ids=[g.goal_id for g in goals]
    if len(set(ids))!=len(ids): raise GameplayContractError("duplicate NPC goal")
    return tuple(sorted((g for g in goals if g.risk_ppm<=maximum_risk_ppm),key=lambda g:(-g.utility_ppm,g.risk_ppm,g.goal_id)))

@dataclass(frozen=True)
class BehaviorNode:
    node_id:str
    kind:str
    children:tuple[str,...]=()
    def __post_init__(self)->None:
        require_id(self.node_id,"node_id")
        if self.kind not in {"selector","sequence","condition","action","decorator"}: raise GameplayContractError("invalid behavior kind")
        children=tuple(self.children)
        if len(set(children))!=len(children) or self.node_id in children: raise GameplayContractError("invalid behavior children")
        for child in children: require_id(child,"behavior child")
        if self.kind in {"condition","action"} and children: raise GameplayContractError("leaf behavior cannot have children")
        object.__setattr__(self,"children",children)
class BehaviorTree:
    def __init__(self,nodes:Sequence[BehaviorNode],root_id:str)->None:
        if not nodes or len(nodes)>MAX_BEHAVIOR_NODES: raise GameplayContractError("behavior node count out of bounds")
        by_id={n.node_id:n for n in nodes}
        if len(by_id)!=len(nodes): raise GameplayContractError("duplicate behavior node")
        root_id=require_id(root_id,"root_id")
        if root_id not in by_id: raise GameplayContractError("unknown behavior root")
        for node in nodes:
            if set(node.children)-set(by_id): raise GameplayContractError("unknown behavior child")
        parents={}
        for node in nodes:
            for child in node.children:
                if child in parents: raise GameplayContractError("behavior node has multiple parents")
                parents[child]=node.node_id
        self._nodes=MappingProxyType(by_id); self.root_id=root_id; self._validate()
    def _validate(self)->None:
        seen=set(); active=set()
        def visit(nid:str)->None:
            if nid in active: raise GameplayContractError("behavior cycle")
            if nid in seen:return
            active.add(nid)
            for child in self._nodes[nid].children: visit(child)
            active.remove(nid); seen.add(nid)
        visit(self.root_id)
        if seen!=set(self._nodes): raise GameplayContractError("disconnected behavior node")

@dataclass(frozen=True)
class CombatAction:
    action_id:str
    damage_units:int
    stamina_cost:int
    cooldown_ticks:int
    def __post_init__(self)->None:
        require_id(self.action_id,"action_id")
        for name in ("damage_units","stamina_cost","cooldown_ticks"):
            v=getattr(self,name)
            if not _is_int(v) or not 0<=v<=MAX_VALUE: raise GameplayContractError(f"invalid {name}")
    def resolve(self,target_health:int,attacker_stamina:int)->tuple[int,int]:
        if not _is_int(target_health) or target_health<0 or not _is_int(attacker_stamina) or attacker_stamina<0: raise GameplayContractError("invalid combat state")
        if attacker_stamina<self.stamina_cost: raise GameplayContractError("insufficient stamina")
        return (max(0,target_health-self.damage_units),attacker_stamina-self.stamina_cost)

@dataclass(frozen=True)
class EconomyRule:
    rule_id:str
    item_id:str
    currency_id:str
    unit_price:int
    max_quantity:int
    def __post_init__(self)->None:
        require_id(self.rule_id,"rule_id"); require_id(self.item_id,"item_id"); require_id(self.currency_id,"currency_id")
        if not _is_int(self.unit_price) or not 0<=self.unit_price<=MAX_VALUE: raise GameplayContractError("invalid unit_price")
        if not _is_int(self.max_quantity) or not 1<=self.max_quantity<=MAX_VALUE: raise GameplayContractError("invalid max_quantity")
    def quote(self,quantity:int)->int:
        if not _is_int(quantity) or not 1<=quantity<=self.max_quantity: raise GameplayContractError("invalid quantity")
        total=self.unit_price*quantity
        if total>MAX_VALUE: raise GameplayContractError("economy value overflow")
        return total

@dataclass(frozen=True)
class GameplaySnapshot:
    sequence:int
    state_digest:str
    world_digest:str
    quest_digest:str
    economy_digest:str
    prior_snapshot_digest:str|None=None
    def __post_init__(self)->None:
        if not _is_int(self.sequence) or self.sequence<0: raise GameplayContractError("invalid snapshot sequence")
        for name in ("state_digest","world_digest","quest_digest","economy_digest"): require_digest(getattr(self,name),name)
        if self.prior_snapshot_digest is not None: require_digest(self.prior_snapshot_digest,"prior_snapshot_digest")
        if self.sequence==0 and self.prior_snapshot_digest is not None: raise GameplayContractError("genesis gameplay snapshot cannot have parent")
        if self.sequence>0 and self.prior_snapshot_digest is None: raise GameplayContractError("gameplay snapshot requires parent")
    @property
    def digest(self)->str:return digest_json(self.__dict__)
