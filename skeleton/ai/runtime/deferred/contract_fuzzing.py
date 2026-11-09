"""Deterministic, resource-bounded contract fuzzing for VOL-198."""
from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Callable, Mapping, Sequence

from .contracts import sha256_json


@dataclass(frozen=True, slots=True)
class FuzzBudget:
    max_cases: int
    max_failures: int

    def __post_init__(self) -> None:
        for name in ("max_cases", "max_failures"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be positive integer")
        if self.max_failures > self.max_cases:
            raise ValueError("max_failures cannot exceed max_cases")


@dataclass(frozen=True, slots=True)
class FuzzFailure:
    contract_id: str
    seed: int
    case_index: int
    input_digest: str
    error_type: str
    error_digest: str

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "contract_id": self.contract_id,
                "seed": self.seed,
                "case_index": self.case_index,
                "input_digest": self.input_digest,
                "error_type": self.error_type,
                "error_digest": self.error_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class FuzzReport:
    contract_id: str
    seed: int
    attempted: int
    failures: tuple[FuzzFailure, ...]
    exhausted_failure_budget: bool

    @property
    def digest(self) -> str:
        return sha256_json(
            {
                "contract_id": self.contract_id,
                "seed": self.seed,
                "attempted": self.attempted,
                "failure_digests": [item.digest for item in self.failures],
                "exhausted_failure_budget": self.exhausted_failure_budget,
            }
        )


class ContractFuzzer:
    """Runs a deterministic generator against a validator with hard case bounds."""

    def __init__(
        self,
        contract_id: str,
        generator: Callable[[random.Random, int], Mapping[str, Any]],
        validator: Callable[[Mapping[str, Any]], None],
    ) -> None:
        if not isinstance(contract_id, str) or not contract_id.strip():
            raise ValueError("contract_id must be non-empty")
        if not callable(generator) or not callable(validator):
            raise TypeError("generator and validator must be callable")
        self.contract_id = contract_id
        self._generator = generator
        self._validator = validator

    def run(self, *, seed: int, budget: FuzzBudget) -> FuzzReport:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be integer")
        rng = random.Random(seed)
        failures: list[FuzzFailure] = []
        attempted = 0
        exhausted = False

        for index in range(budget.max_cases):
            raw = self._generator(rng, index)
            if not isinstance(raw, Mapping):
                raise TypeError("fuzz generator must return a mapping")
            case = dict(raw)
            attempted += 1
            try:
                self._validator(case)
            except Exception as exc:
                error_type = type(exc).__name__
                failures.append(
                    FuzzFailure(
                        contract_id=self.contract_id,
                        seed=seed,
                        case_index=index,
                        input_digest=sha256_json(case),
                        error_type=error_type,
                        error_digest=sha256_json(
                            {"type": error_type, "message": str(exc)}
                        ),
                    )
                )
                if len(failures) >= budget.max_failures:
                    exhausted = True
                    break

        return FuzzReport(
            contract_id=self.contract_id,
            seed=seed,
            attempted=attempted,
            failures=tuple(failures),
            exhausted_failure_budget=exhausted,
        )

    def reproduce(
        self,
        failure: FuzzFailure,
    ) -> FuzzFailure:
        if failure.contract_id != self.contract_id:
            raise ValueError("failure belongs to a different contract")
        report = self.run(
            seed=failure.seed,
            budget=FuzzBudget(
                max_cases=failure.case_index + 1,
                max_failures=failure.case_index + 1,
            ),
        )
        matches = [
            item
            for item in report.failures
            if item.case_index == failure.case_index
        ]
        if not matches or matches[0].digest != failure.digest:
            raise RuntimeError("fuzz failure is not reproducible")
        return matches[0]
