"""Interactive quest and dialogue runtime: capabilities 041–050.

Deterministic branching, prerequisites, dialogue consequences and durable
portable story-state. No LLM-generated dialogue is trusted as executable code.
"""
from __future__ import annotations
from dataclasses import dataclass,replace
from hashlib import sha256
import json
import random

@dataclass(frozen=True)
class Objective:
    key: str
    kind: str
    target: str
    required: int
    optional: bool = False

@dataclass(frozen=True)
class Quest:
    key: str
    name: str
    objectives: tuple[Objective,...]
    prerequisites: tuple[str,...] = ()
    reward_coins: int = 0

@dataclass(frozen=True)
class QuestProgress:
    key: str
    counters: tuple[tuple[str,int],...] = ()
    state: str = "locked"

@dataclass(frozen=True)
class DialogueChoice:
    label: str
    destination: str
    requires_flag: str = ""
    sets_flag: str = ""
    reputation_delta: int = 0

@dataclass(frozen=True)
class DialogueNode:
    key: str
    speaker: str
    text: str
    choices: tuple[DialogueChoice,...] = ()

@dataclass(frozen=True)
class StoryState:
    flags: frozenset[str] = frozenset()
    visited: tuple[str,...] = ()
    reputation: tuple[tuple[str,int],...] = ()
    choices: tuple[tuple[str,str],...] = ()

# 041 Create a finite quest with actual tracked objectives.
def define_quest(key:str,name:str,objectives:tuple[Objective,...], *,
                 prerequisites:tuple[str,...]=(),reward:int=0)->Quest:
    if not key or not name or not objectives or len(objectives)>30 or not 0<=reward<=1000000:
        raise ValueError("invalid quest")
    if len({o.key for o in objectives})!=len(objectives) or key in prerequisites:
        raise ValueError("duplicate objectives or self-dependent quest")
    if any(o.kind not in ("collect","defeat","visit","talk","craft","activate") or
           not 1<=o.required<=100000 for o in objectives):
        raise ValueError("invalid objective")
    return Quest(key,name,objectives,prerequisites,reward)

# 042 Order the quest campaign and reject cycles before play.
def schedule_quest_dependencies(quests:tuple[Quest,...])->tuple[str,...]:
    lookup={q.key:q for q in quests}
    if len(lookup)!=len(quests) or len(quests)>1000:
        raise ValueError("invalid quest campaign")
    state={};ordered=[]
    def visit(key):
        if key not in lookup:raise ValueError("unknown prerequisite")
        if state.get(key)==1:raise ValueError("cyclic quest dependency")
        if state.get(key)==2:return
        state[key]=1
        for dep in lookup[key].prerequisites:visit(dep)
        state[key]=2;ordered.append(key)
    for key in sorted(lookup):visit(key)
    return tuple(ordered)

# 043 Activate newly available quests when prerequisites are completed.
def activate_available_quests(quests:tuple[Quest,...],
                              progress:tuple[QuestProgress,...]
                              )->tuple[QuestProgress,...]:
    finished={q.key for q in progress if q.state=="complete"}
    state={q.key:q for q in progress}
    for quest in quests:
        old=state.get(quest.key,QuestProgress(quest.key))
        if old.state=="locked" and set(quest.prerequisites)<=finished:
            state[quest.key]=replace(old,state="active")
    return tuple(sorted(state.values(),key=lambda q:q.key))

# 044 Apply gameplay events to active objective counters only.
def apply_quest_event(quest:Quest,progress:QuestProgress, *, kind:str,
                      target:str,quantity:int=1)->QuestProgress:
    if progress.key!=quest.key or quantity<1 or quantity>100000:
        raise ValueError("invalid quest event")
    if progress.state!="active":return progress
    counters=dict(progress.counters)
    for obj in quest.objectives:
        if obj.kind==kind and obj.target==target:
            counters[obj.key]=min(obj.required,counters.get(obj.key,0)+quantity)
    return replace(progress,counters=tuple(sorted(counters.items())))

# 045 Finish a quest only when all mandatory objectives truly completed.
def complete_quest(quest:Quest,progress:QuestProgress)->tuple[QuestProgress,int]:
    if progress.key!=quest.key or progress.state!="active":
        raise ValueError("quest not active")
    counts=dict(progress.counters)
    if any(counts.get(o.key,0)<o.required for o in quest.objectives if not o.optional):
        raise ValueError("quest objective incomplete")
    return replace(progress,state="complete"),quest.reward_coins

# 046 Select dialogue options based on acquired story flags.
def available_dialogue_choices(node:DialogueNode,state:StoryState
                               )->tuple[DialogueChoice,...]:
    return tuple(choice for choice in node.choices
                 if not choice.requires_flag or choice.requires_flag in state.flags)

# 047 Traverse actual dialogue branch and record consequences.
def advance_dialogue(node:DialogueNode,choice_index:int,
                     graph:dict[str,DialogueNode],state:StoryState,
                     *, faction:str="world")->tuple[DialogueNode,StoryState]:
    allowed=available_dialogue_choices(node,state)
    if not 0<=choice_index<len(allowed):
        raise ValueError("dialogue choice unavailable")
    chosen=allowed[choice_index]
    if chosen.destination not in graph:
        raise ValueError("dangling dialogue destination")
    flags=set(state.flags)
    if chosen.sets_flag:flags.add(chosen.sets_flag)
    standing=dict(state.reputation)
    standing[faction]=max(-100,min(100,standing.get(faction,0)+chosen.reputation_delta))
    updated=replace(state,flags=frozenset(flags),
                    visited=state.visited+(node.key,),
                    reputation=tuple(sorted(standing.items())),
                    choices=state.choices+((node.key,chosen.destination),))
    return graph[chosen.destination],updated

# 048 Build a small original branching story tied to real quest flags.
def generate_dialogue_arc(*, topic:str,seed:int,objectives:tuple[str,...]
                          )->dict[str,DialogueNode]:
    if not topic or len(topic)>120 or len(objectives)>10:
        raise ValueError("invalid dialogue arc")
    rng=random.Random(seed)
    narrator=rng.choice(("Caretaker","Explorer","Engineer","Archivist"))
    nodes={
        "intro":DialogueNode("intro",narrator,
            f"The {topic} needs attention. Will you help?",(
                DialogueChoice("I will investigate.","accept",sets_flag="quest_accepted",reputation_delta=2),
                DialogueChoice("Not right now.","decline"),
            )),
        "accept":DialogueNode("accept",narrator,
            "Find the clues and return when you are ready."),
        "decline":DialogueNode("decline",narrator,
            "The work remains unfinished."),
    }
    for index,name in enumerate(objectives):
        key=f"clue_{index}"
        nodes[key]=DialogueNode(key,narrator,f"Study this: {name}.",(
            DialogueChoice("I understand.","accept",sets_flag=f"clue_seen_{index}"),
        ))
    return nodes

# 049 Shift reputation with a deterministic faction-specific rule.
def update_faction_reputation(state:StoryState,faction:str,delta:int,
                              *, lower:int=-100,upper:int=100)->StoryState:
    if not faction or not -1000<=delta<=1000 or lower>=upper:
        raise ValueError("invalid reputation update")
    reputation=dict(state.reputation)
    reputation[faction]=max(lower,min(upper,reputation.get(faction,0)+delta))
    return replace(state,reputation=tuple(sorted(reputation.items())))

# 050 Serialize and recover player story choices with integrity digest.
def story_save_slot(state:StoryState)->dict[str,object]:
    payload={
        "flags":sorted(state.flags),"visited":list(state.visited),
        "reputation":list(state.reputation),"choices":list(state.choices),
    }
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"))
    return {"schema":"skeleton.original_story.v1",
            "state":payload,"sha256":sha256(raw.encode()).hexdigest()}

def restore_story_slot(slot:dict[str,object])->StoryState:
    if slot.get("schema")!="skeleton.original_story.v1":
        raise ValueError("unknown save schema")
    payload=slot["state"]
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"))
    if sha256(raw.encode()).hexdigest()!=slot.get("sha256"):
        raise ValueError("corrupt story save")
    if any(len(payload[k])>10000 for k in ("flags","visited","reputation","choices")):
        raise ValueError("story save exceeds capacity")
    return StoryState(frozenset(payload["flags"]),tuple(payload["visited"]),
                      tuple((str(k),int(n)) for k,n in payload["reputation"]),
                      tuple((str(k),str(v)) for k,v in payload["choices"]))
