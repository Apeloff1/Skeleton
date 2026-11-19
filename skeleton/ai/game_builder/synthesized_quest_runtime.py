"""Actual location/interaction-gated objective execution and independently pinned replay."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from skeleton.app.recovered_evidence import EvidenceError, array, fields, identifier, seal, verify
from .quest_objective_runtime import QuestDefinition, QuestRuntime, ObjectiveState
from .synthesized_quest_model import load_order, MAX_MOVES, MAX_STEPS
from .synthesized_quest_planner import plan_campaign

SAVE_SCHEMA="skeleton.synthesized-quest.save.v1"
MAX_ACTIONS=MAX_MOVES+MAX_STEPS*3+16


@dataclass
class Campaign:
    order: object
    plan: dict
    runtime: QuestRuntime
    location: str
    spoken: set
    actions: list
    ledger: list
    abandoned: bool=False

    @classmethod
    def start(cls,document,plan,*,expected_plan_digest,authorized):
        if authorized is not True:
            raise PermissionError("explicit local operator required")
        verify(plan,expected_plan_digest)
        if plan_campaign(document,authorized=True)!=plan:
            raise EvidenceError("plan differs from canonical synthesis")
        order=load_order(document)
        definition=QuestDefinition.from_mapping(plan["definition"])
        return cls(order,deepcopy(plan),QuestRuntime(definition),order.world.start,set(),[],[])

    def apply(self,action):
        if self.abandoned or self.runtime.status!="in_progress" or len(self.actions)>=MAX_ACTIONS:
            raise EvidenceError("terminal campaign or action ceiling")
        if type(action) is not dict:
            raise EvidenceError("action object required")
        op=action.get("op")
        if op=="move":
            fields(action,{"op","destination"})
            dest=identifier(action["destination"])
            if dest not in self.order.world.edges[self.location]:
                raise EvidenceError("movement not on authored edge")
            self.location=dest
        elif op=="talk":
            fields(action,{"op","npc"})
            npc=identifier(action["npc"])
            if self.order.world.npcs.get(npc)!=self.location:
                raise EvidenceError("NPC not here")
            active=[step["id"] for step in self.plan["quest"]["steps"]
                    if step["npc"]==npc and step["location"]==self.location
                    and self.runtime.states[step["id"]] is ObjectiveState.ACTIVE]
            if not active or all(x in self.spoken for x in active):
                raise EvidenceError("no pending conversation")
            self.spoken.update(active)
        elif op=="complete":
            fields(action,{"op","objective"})
            oid=identifier(action["objective"])
            step=next((s for s in self.plan["quest"]["steps"] if s["id"]==oid),None)
            if step is None or self.runtime.states[oid] is not ObjectiveState.ACTIVE:
                raise EvidenceError("objective not active")
            if step["location"]!=self.location or (step["npc"] is not None and oid not in self.spoken):
                raise EvidenceError("location or conversation witness missing")
            self.runtime.advance(oid)
            self.ledger.extend({"objective":oid,"index":i,**r} for i,r in enumerate(step["rewards"]))
        elif op=="abandon":
            fields(action,{"op"})
            self.runtime.signal("campaign_abandoned")
            self.abandoned=True
        else:
            raise EvidenceError("unknown campaign action")
        self.actions.append(deepcopy(action))

    def snapshot(self):
        totals={}
        for row in self.ledger:
            totals[row["kind"]]=totals.get(row["kind"],0)+row["amount"]
        if (sum(totals.values())>self.order.policy.max_total_reward or
            self.runtime.earned_rewards()!=[{"kind":r["kind"],"amount":r["amount"]} for r in self.ledger]):
            raise EvidenceError("canonical reward reconciliation failed")
        return seal({"schema":SAVE_SCHEMA,"plan_digest":self.plan["digest"],
                     "status":self.runtime.status,"location":self.location,
                     "spoken_objectives":sorted(self.spoken),"actions":deepcopy(self.actions),
                     "quest_runtime":self.runtime.snapshot(),"reward_ledger":deepcopy(self.ledger),
                     "reward_totals":dict(sorted(totals.items())),"abandoned":self.abandoned,
                     "native_engine_executed":False,"release_certified":False})

    @classmethod
    def restore(cls,document,plan,snapshot,*,expected_plan_digest,expected_save_digest,authorized):
        if authorized is not True:
            raise PermissionError("explicit local operator required")
        verify(snapshot,expected_save_digest)
        if snapshot.get("schema")!=SAVE_SCHEMA:
            raise EvidenceError("unsupported save")
        run=cls.start(document,plan,expected_plan_digest=expected_plan_digest,authorized=True)
        for action in array(snapshot.get("actions"),0,MAX_ACTIONS):
            run.apply(action)
        owner=QuestRuntime.restore(run.runtime.definition,snapshot["quest_runtime"])
        if owner.snapshot()!=run.runtime.snapshot() or run.snapshot()!=snapshot:
            raise EvidenceError("save differs from replay")
        return run


def solution(plan):
    actions=[]
    for route,step in zip(plan["routes"],plan["quest"]["steps"],strict=True):
        actions.extend({"op":"move","destination":loc} for loc in route["waypoints"][1:])
        if step["npc"] is not None:
            actions.append({"op":"talk","npc":step["npc"]})
        actions.append({"op":"complete","objective":step["id"]})
    if len(actions)>MAX_ACTIONS:
        raise EvidenceError("solution ceiling")
    return actions


def qualify_campaign(document,*,authorized):
    plan=plan_campaign(document,authorized=authorized)
    run=Campaign.start(document,plan,expected_plan_digest=plan["digest"],authorized=True)
    actions=solution(plan)
    midpoint=len(actions)//2
    for action in actions[:midpoint]:
        run.apply(action)
    checkpoint=run.snapshot()
    other=Campaign.restore(document,plan,checkpoint,expected_plan_digest=plan["digest"],
                           expected_save_digest=checkpoint["digest"],authorized=True)
    for action in actions[midpoint:]:
        run.apply(action)
        other.apply(action)
    final=run.snapshot()
    if final["status"]!="completed" or other.snapshot()!=final:
        raise EvidenceError("campaign completion or reconstruction failed")
    return seal({"schema":"skeleton.synthesized-quest.qualification.v1","plan":plan,
                 "checkpoint_digest":checkpoint["digest"],"final":final,
                 "replayed_actions":len(actions),"canonical_quest_executed":True,
                 "log_reconstructed":True,"process_restart_tested":False,
                 "native_engine_executed":False,"release_certified":False})
