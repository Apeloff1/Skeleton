"""Finite model evaluation, evidence reconciliation and Wilson lower bounds."""
from __future__ import annotations
import math
from dataclasses import dataclass
from .contracts import identifier,integer,number,sha,refuse
@dataclass(frozen=True,slots=True)
class EvaluationCase:
    case_id:str
    input_sha256:str
    expected_sha256:str
    observed_sha256:str
    approved:bool
    def __post_init__(self):
        identifier(self.case_id)
        sha(self.input_sha256);sha(self.expected_sha256);sha(self.observed_sha256)
        if type(self.approved) is not bool:refuse("external approval claim requires explicit boolean")
    def passed(self):
        return self.approved and self.expected_sha256==self.observed_sha256
def wilson_lower(passed,total,*,z=1.96):
    integer(passed,maximum=100000000)
    integer(total,minimum=1,maximum=100000000)
    if passed>total:refuse("successes cannot exceed evaluated cases")
    z=number(z,minimum=0.001,maximum=10)
    p=passed/total;z2=z*z
    return max(0.0,(p+z2/(2*total)-z*math.sqrt(
        (p*(1-p)+z2/(4*total))/total))/(1+z2/total))
def evaluate(cases,*,min_cases=1,min_lower_bound=0):
    integer(min_cases,minimum=1,maximum=1000000)
    min_lower_bound=number(min_lower_bound,minimum=0,maximum=1)
    if type(cases) not in (tuple,list) or len(cases)>1000000:
        refuse("bounded independent evaluation cases required")
    if len({case.case_id for case in cases})!=len(cases):
        refuse("duplicate benchmark case identities")
    for case in cases:
        if type(case) is not EvaluationCase:refuse("typed evaluation case required")
    total=len(cases);passed=sum(case.passed() for case in cases)
    lower=wilson_lower(passed,total) if total else 0.0
    return {"cases":total,"passed":passed,"failed":total-passed,
            "pass_rate":passed/total if total else 0,
            "wilson_lower":lower,
            "sample_floor_met":total>=min_cases,
            "threshold_met":total>=min_cases and lower>=min_lower_bound,
            "native_model_proved":False}
def confusion(rows):
    if type(rows) not in (tuple,list) or len(rows)>1000000:
        refuse("bounded classifier rows required")
    counts={"tp":0,"fp":0,"tn":0,"fn":0}
    for expected,observed in rows:
        if type(expected) is not bool or type(observed) is not bool:
            refuse("explicit classification truth labels required")
        key=("t" if expected==observed else "f")+("p" if observed else "n")
        counts[key]+=1
    tp,fp,tn,fn=(counts[k] for k in ("tp","fp","tn","fn"))
    precision=tp/(tp+fp) if tp+fp else 0.0
    recall=tp/(tp+fn) if tp+fn else 0.0
    return {**counts,"precision":precision,"recall":recall,
            "f1":2*precision*recall/(precision+recall) if precision+recall else 0}
