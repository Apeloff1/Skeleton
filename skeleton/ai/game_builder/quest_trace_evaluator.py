"""Immutable-source quest trace diagnosis.

Only player action traces are candidates. World, quest plan, schedule,
policy and reward definitions are never repair targets. Every outcome
is derived from the canonical campaign state, not declared by the caller.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from skeleton.app.recovered_evidence import EvidenceError, array, fields, integer, digest, verify
from skeleton.ai.game_builder.synthesized_quest_planner import plan_campaign
from skeleton.ai.game_builder.synthesized_quest_runtime import Campaign, MAX_ACTIONS
from skeleton.ai.game_builder.synthesized_quest_model import shortest_route
from skeleton.ai.game_builder.quest_objective_runtime import ObjectiveState
from skeleton.gameforge.batch_b039.self_repair import EvalFailure, EvalResult

MAX_REPAIR_ACTIONS=512
MAX_CANDIDATES=64
MAX_EVALUATED_ACTIONS=64_000


@dataclass
class TraceObservation:
    run: Campaign
    accepted_prefix: int
    total_actions: int
    completed: int
    result: EvalResult
    failure_code: str | None

    @property
    def passed(self):
        return self.result.passed


class TraceEvaluator:
    def __init__(self,document,plan,expected_digest):
        verify(plan,expected_digest)
        if plan_campaign(document,authorized=True)!=plan:
            raise EvidenceError("repair plan differs from canonical source")
        self.document=deepcopy(document)
        self.plan=deepcopy(plan)
        self.expected_digest=expected_digest
        self.calls=0
        self.attempted_actions=0
        self.observations=[]

    def observe(self,artifact):
        fields(artifact,{"actions"})
        actions=array(artifact["actions"],0,MAX_REPAIR_ACTIONS)
        if self.calls>=MAX_CANDIDATES or self.attempted_actions+len(actions)>MAX_EVALUATED_ACTIONS:
            raise EvidenceError("trace evaluation work ceiling")
        self.calls+=1
        self.attempted_actions+=len(actions)
        run=Campaign.start(self.document,self.plan,expected_plan_digest=self.expected_digest,authorized=True)
        accepted=0
        code=None
        for action in actions:
            try:
                run.apply(action)
            except (ValueError,TypeError,KeyError):
                code="invalid_action"
                break
            accepted+=1
        completed=sum(state is ObjectiveState.COMPLETED for state in run.runtime.states.values())
        full=run.runtime.status=="completed" and accepted==len(actions)
        if code is None and not full:
            code="abandoned" if run.runtime.status=="failed" else "unfinished"
        if full:
            score=1.0
            failures=()
        else:
            # Primary progress is canonical completed objectives. A valid
            # prefix is secondary and terminal failures cannot gain credit.
            objectives=len(self.plan["quest"]["steps"])
            score=(completed/(objectives+1))*0.9
            if run.runtime.status=="in_progress":
                score+=0.075*accepted/(MAX_REPAIR_ACTIONS+1)
            if accepted==len(actions) and run.runtime.status=="in_progress":
                score+=0.01
            failures=(EvalFailure("rule."+code,"canonical gameplay rule not satisfied"),)
        result=EvalResult(score=score,failures=failures)
        self.observations.append({"candidate_sha256":digest(artifact),
                                  "accepted_prefix":accepted,"actions":len(actions),
                                  "objective_count":completed,"score":score,"passed":full,
                                  "failure_code":code})
        return TraceObservation(run,accepted,len(actions),completed,result,code)

    def evaluate(self,artifact):
        return self.observe(artifact).result

    def proposed_suffix(self,observation):
        run=observation.run
        if run.runtime.status!="in_progress":
            return None
        current=run.location
        suffix=[]
        for step in self.plan["quest"]["steps"]:
            oid=step["id"]
            if run.runtime.states[oid] is ObjectiveState.COMPLETED:
                continue
            route=shortest_route(run.order.world,current,step["location"])
            suffix.extend({"op":"move","destination":location} for location in route[1:])
            if step["npc"] is not None and oid not in run.spoken:
                suffix.append({"op":"talk","npc":step["npc"]})
            suffix.append({"op":"complete","objective":oid})
            current=step["location"]
            if len(suffix)>MAX_REPAIR_ACTIONS:
                return None
        return suffix
