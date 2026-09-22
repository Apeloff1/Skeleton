"""Bounded history of AI shell evaluation and regression runs."""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Callable

from skeleton.shells.ai.eval_runner import AIEvalRun


@dataclass(frozen=True)
class RegressionRecord:
    sequence: int
    run: AIEvalRun
    observed_at: float
    baseline_digest: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "observed_at": self.observed_at,
            "baseline_digest": self.baseline_digest,
            "run": self.run.to_dict(),
        }


@dataclass(frozen=True)
class RegressionComparison:
    current_pass_rate: float
    baseline_pass_rate: float
    delta: float
    regressed_cases: tuple[str, ...]
    improved_cases: tuple[str, ...]

    @property
    def regressed(self) -> bool:
        return self.delta < 0 or bool(self.regressed_cases)

    def to_dict(self) -> dict[str, object]:
        return {
            "current_pass_rate": self.current_pass_rate,
            "baseline_pass_rate": self.baseline_pass_rate,
            "delta": self.delta,
            "regressed_cases": list(self.regressed_cases),
            "improved_cases": list(self.improved_cases),
            "regressed": self.regressed,
        }


class AIRegressionHistory:
    def __init__(
        self,
        *,
        max_runs: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_runs <= 0:
            raise ValueError("max_runs must be positive")
        self.max_runs = max_runs
        self._clock = clock
        self._items: list[RegressionRecord] = []
        self._lock = threading.RLock()

    def record(self, run: AIEvalRun, *, baseline_digest: str = "") -> RegressionRecord:
        with self._lock:
            item = RegressionRecord(
                (self._items[-1].sequence + 1) if self._items else 1,
                run,
                self._clock(),
                baseline_digest,
            )
            self._items.append(item)
            if len(self._items) > self.max_runs:
                self._items = self._items[-self.max_runs :]
            return item

    @staticmethod
    def compare(current: AIEvalRun, baseline: AIEvalRun) -> RegressionComparison:
        baseline_cases = {item.case_id: item for item in baseline.cases}
        current_cases = {item.case_id: item for item in current.cases}
        regressed = []
        improved = []
        for case_id in sorted(set(baseline_cases) & set(current_cases)):
            before = baseline_cases[case_id].passed
            after = current_cases[case_id].passed
            if before and not after:
                regressed.append(case_id)
            if not before and after:
                improved.append(case_id)
        return RegressionComparison(
            current.pass_rate,
            baseline.pass_rate,
            current.pass_rate - baseline.pass_rate,
            tuple(regressed),
            tuple(improved),
        )

    def snapshot(self) -> tuple[RegressionRecord, ...]:
        with self._lock:
            return tuple(self._items)
