"""Versioned executable 672-case durable-queue acceptance matrix.

Each fixture is a stable declarative operation; outcomes come from executing
actual JobStore, SQLite, native bridge boundaries and operator gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from .canonical import decode
from .case_oracle import evaluate

DOMAINS=(
    "identity","work_limits","job_contract","model_binding","submission",
    "dedup","capacity","claim","heartbeat","completion","result_limits",
    "cancellation","failure","sweep","dependencies","fairness",
    "audit","recovery","admission","cursor","observer",
)
CASES_PER_DOMAIN=32
TOTAL_CASES=len(DOMAINS)*CASES_PER_DOMAIN


@dataclass(frozen=True, slots=True)
class Evaluation:
    scenario_id:str
    domain:str
    expected_allow:bool
    actual_allow:bool
    expected_state:str|None
    actual_state:str|None
    actual_code:str|None

    @property
    def passed(self)->bool:
        return (self.expected_allow is self.actual_allow and
                (not self.expected_allow or self.expected_state==self.actual_state))


def iter_cases():
    base=resources.files(__package__)/"scenarios"
    seen=set()
    for domain in DOMAINS:
        directory=base/domain
        cases=sorted(directory.iterdir(),key=lambda item:item.name)
        if len(cases)!=CASES_PER_DOMAIN:
            raise AssertionError("missing or extra scenario in "+domain)
        for path in cases:
            if path.suffix!=".json":
                raise AssertionError("unexpected scenario artifact")
            case=decode(path.read_bytes())
            if type(case) is not dict or case.get("schema")!="skeleton.ai.jobs.case.v1":
                raise AssertionError("invalid scenario schema")
            if case.get("domain")!=domain:
                raise AssertionError("scenario domain mismatch")
            if type(case.get("expected_allow")) is not bool:
                raise AssertionError("scenario expectation not boolean")
            if type(case.get("input")) is not dict:
                raise AssertionError("scenario input malformed")
            sid=case.get("id")
            if not isinstance(sid,str) or not sid.startswith(domain+"-") or sid in seen:
                raise AssertionError("scenario identity mismatch")
            if not isinstance(case.get("threat"),str) or not case["threat"]:
                raise AssertionError("missing risk statement")
            seen.add(sid)
            yield case
    if len(seen)!=TOTAL_CASES:
        raise AssertionError("missing case inventory")


def run_matrix()->dict:
    failures=[]
    observed=0
    for case in iter_cases():
        outcome=evaluate(case["domain"],case["input"])
        actual_allow=outcome["allowed"]
        expected_allow=case["expected_allow"]
        actual_state=outcome.get("state")
        if actual_allow is not expected_allow or (
           expected_allow and case.get("expected_state")!=actual_state
        ):
            failures.append({"id":case["id"],"expected_allow":expected_allow,
                             "actual_allow":actual_allow,
                             "expected_state":case.get("expected_state"),
                             "actual_state":actual_state,
                             "actual_code":outcome.get("code")})
        observed+=1
    return {
      "schema":"skeleton.ai.jobs.suite.v1","total":observed,
      "passed":observed-len(failures),"failed":len(failures),
      "failures":failures[:64],
      "real_model_tested":False,"native_device_qualified":False,
      "release_certified":False,
    }
