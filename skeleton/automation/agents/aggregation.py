"""Agent aggregation — combine multi-agent results into one answer."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from skeleton.kernel.errors import AgentError


class AggregationError(AgentError):
    code = "AGT.AGGREGATION"


@dataclass(frozen=True)
class Estimate:
    agent: str
    value: Any
    weight: float = 1.0


class Aggregator:
    """Pluggable reducers over (agent, value) estimates."""

    def __init__(self) -> None:
        self._strategies: Dict[str, Callable[[List[Estimate]], Any]] = {
            "mean": self._mean,
            "weighted": self._weighted,
            "majority": self._majority,
            "max": self._max,
        }

    def register_strategy(self, name: str, fn: Callable[[List[Estimate]], Any]) -> None:
        self._strategies[name] = fn

    def aggregate(self, estimates: List[Estimate], strategy: str = "weighted") -> Any:
        fn = self._strategies.get(strategy)
        if fn is None:
            raise AggregationError("unknown strategy", context={"strategy": strategy})
        return fn(estimates)

    def _mean(self, estimates: List[Estimate]) -> float:
        values = [float(e.value) for e in estimates]
        return sum(values) / max(len(values), 1)

    def _weighted(self, estimates: List[Estimate]) -> float:
        total_weight = sum(e.weight for e in estimates) or 1.0
        return sum(float(e.value) * e.weight for e in estimates) / total_weight

    def _majority(self, estimates: List[Estimate]) -> Any:
        votes = Counter(e.value for e in estimates)
        best, _ = votes.most_common(1)[0]
        return best

    def _max(self, estimates: List[Estimate]) -> float:
        if not estimates:
            raise AggregationError("no estimates")
        return max(float(e.value) for e in estimates)
