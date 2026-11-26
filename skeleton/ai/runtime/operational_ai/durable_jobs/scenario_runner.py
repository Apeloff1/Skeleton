"""Versioned executable 672-case durable-queue acceptance matrix.

Each fixture is a stable declarative operation; outcomes come from executing
actual JobStore, SQLite, native bridge boundaries and operator gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json

from .canonical import MAX_BYTES, decode
from .errors import JobDenied
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


def _read_case(path):
    data = path.read_bytes()
    if len(data) <= MAX_BYTES:
        return decode(data)
    # Preserve production JSON limits. This one negative native-output fixture
    # deliberately exceeds them and must still reach the actual receipt validator.
    if path.name != "result_limits-28.json" or len(data) > 300000:
        raise JobDenied("json-oversize")

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise JobDenied("json-duplicate")
            result[key] = value
        return result

    case = json.loads(data.decode("utf-8"), object_pairs_hook=unique_pairs)
    if (type(case) is not dict or case.get("schema") != "skeleton.ai.jobs.case.v1"
        or case.get("domain") != "result_limits"
        or case.get("id") != "result_limits-28"
        or case.get("expected_allow") is not False
        or type(case.get("input")) is not dict
        or type(case["input"].get("text")) is not str
        or len(case["input"]["text"].encode("utf-8")) <= 262144):
        raise JobDenied("json-oversize")
    return case


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
            case=_read_case(path)
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
            # This exact source-owned vector crosses the runtime JSON envelope.
            # Decode its bounded recipe first, then pass identical expanded bytes
            # to the actual policy/receipt boundary. Never relax ingress limits.
            if sid == "result_limits-28":
                recipe = case["input"].get("text")
                if (type(recipe) is not dict or set(recipe) != {"repeat_ascii", "count"}
                        or recipe["repeat_ascii"] != "x"
                        or type(recipe["count"]) is not int or recipe["count"] != 262145
                        or case["expected_allow"] is not False):
                    raise AssertionError("invalid bounded oversized scenario recipe")
                case["input"]["text"] = "x" * 262145
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
