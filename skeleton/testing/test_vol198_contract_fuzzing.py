from __future__ import annotations

import pytest

from skeleton.ai.runtime.deferred.contract_fuzzing import (
    ContractFuzzer,
    FuzzBudget,
)


def generator(rng, index):
    return {"index": index, "value": rng.randrange(0, 10)}


def validator(case):
    if case["value"] >= 5:
        raise ValueError(f"too large:{case['value']}")


def test_fuzzer_is_seed_deterministic_and_report_is_stable() -> None:
    fuzzer = ContractFuzzer("demo.v1", generator, validator)
    first = fuzzer.run(seed=42, budget=FuzzBudget(20, 4))
    second = fuzzer.run(seed=42, budget=FuzzBudget(20, 4))
    assert first == second
    assert first.digest == second.digest
    assert first.attempted <= 20
    assert len(first.failures) <= 4


def test_fuzzer_stops_at_failure_budget() -> None:
    fuzzer = ContractFuzzer(
        "always-fails",
        lambda rng, index: {"index": index},
        lambda case: (_ for _ in ()).throw(ValueError("boom")),
    )
    report = fuzzer.run(seed=1, budget=FuzzBudget(100, 3))
    assert report.attempted == 3
    assert len(report.failures) == 3
    assert report.exhausted_failure_budget is True


def test_failure_reproduction_replays_exact_seed_and_case() -> None:
    fuzzer = ContractFuzzer("demo.v1", generator, validator)
    report = fuzzer.run(seed=9, budget=FuzzBudget(30, 2))
    assert report.failures
    failure = report.failures[0]
    assert fuzzer.reproduce(failure) == failure


def test_reproducer_rejects_cross_contract_failure() -> None:
    first = ContractFuzzer("one", generator, validator)
    second = ContractFuzzer("two", generator, validator)
    failure = first.run(seed=9, budget=FuzzBudget(30, 1)).failures[0]
    with pytest.raises(ValueError, match="different contract"):
        second.reproduce(failure)


def test_fuzzer_rejects_unbounded_or_invalid_budget() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        FuzzBudget(0, 1)
    with pytest.raises(ValueError, match="cannot exceed"):
        FuzzBudget(1, 2)


def test_generator_must_return_mapping() -> None:
    fuzzer = ContractFuzzer("bad-generator", lambda rng, index: index, validator)
    with pytest.raises(TypeError, match="mapping"):
        fuzzer.run(seed=1, budget=FuzzBudget(1, 1))
