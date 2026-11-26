"""Oversized repository vectors reach the live denial boundary, not the fixture decoder."""
import pytest

from skeleton.ai.runtime.operational_ai.durable_jobs.canonical import decode
from skeleton.ai.runtime.operational_ai.durable_jobs.case_oracle import evaluate as evaluate_job
from skeleton.ai.runtime.operational_ai.durable_jobs.errors import JobDenied
from skeleton.ai.runtime.operational_ai.durable_jobs.scenario_runner import iter_cases, TOTAL_CASES
from skeleton.ai.runtime.operational_ai.guarded_request.contracts import parse_json
from skeleton.ai.runtime.operational_ai.guarded_request.errors import GateDenied
from skeleton.ai.runtime.operational_ai.guarded_request.policy_oracle import evaluate as evaluate_guard
from skeleton.ai.runtime.operational_ai.guarded_request.scenario_runner import iter_scenarios, TOTAL_SCENARIOS


def test_durable_oversize_vector_reaches_result_constructor():
    cases = list(iter_cases())
    assert len(cases) == TOTAL_CASES == 672
    case = next(c for c in cases if c["id"] == "result_limits-28")
    assert case["input"]["text"] == "x" * 262145
    assert evaluate_job(case["domain"], case["input"]) == {"allowed": False, "code": "text-output"}
    with pytest.raises(JobDenied, match="json-oversize"):
        decode(b'"' + b'x' * 262145 + b'"')


def test_guarded_prompt_boundary_reaches_native_token_fence():
    cases = list(iter_scenarios())
    assert len(cases) == TOTAL_SCENARIOS == 384
    by_id = {c["id"]: c for c in cases}
    valid, invalid = by_id["tokens-10"], by_id["tokens-24"]
    assert valid["input"]["prompt"] == "x" * 32768
    assert invalid["input"]["prompt"] == "x" * 32769
    assert evaluate_guard(valid["control"], valid["input"])["allowed"] is True
    assert evaluate_guard(invalid["control"], invalid["input"]) == {"allowed": False, "code": "prompt-text"}
    with pytest.raises(GateDenied, match="json-text"):
        parse_json('"' + 'x' * 32769 + '"')
