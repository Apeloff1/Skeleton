"""Hive aggregation — collective estimation that beats the best single agent.

Condorcet's jury theorem and Galton's ox-weighing crowd share one insight:
aggregated independent judgments outperform individual experts, *provided
the errors are independent and the aggregation respects competence*. The
swarm already tracks per-agent reputation and per-dimension capability;
this module turns that bookkeeping into a collective-intelligence engine.

Three estimators, in increasing sophistication:

  1. **Mean** — the naive crowd answer; robust when agents are exchangeable.
  2. **Reputation-weighted** — estimates weighted by reputation * the
     relevant capability dimension, so the oracle agents count more on
     prediction tasks and workers on estimation.
  3. **Trimmed weighted** — drop the outer quartiles first; a Byzantine
     agent voting extreme values can't drag the answer (composes with the
     BFT consensus already in the package).

Every aggregation reports a **diversity score** (coefficient of variation
across estimates): high consensus is trustworthy, high dispersion means the
hive disagrees and the caller should gather more agents or distrust the
number. Deterministic given the same inputs; pure domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from skeleton.kernel.errors import AgentError
from skeleton.kernel.events import DomainEvent, EventBus


class AggregationError(AgentError):
    code = "AGT.AGGREGATION"
    http_status = 422


@dataclass(frozen=True)
class Estimate:
    """One agent's answer to one question."""
    agent_id: str
    value: float
    weight: float = 1.0            # caller-supplied (reputation * capability)


@dataclass(frozen=True)
class HiveResult:
    """The aggregated answer with its confidence metadata."""
    value: float
    method: str
    n_estimates: int
    n_used: int
    diversity: float               # coefficient of variation; 0 = unanimity
    spread: float                  # max - min of used estimates
    trustworthy: bool              # diversity below the trust ceiling


class HiveMind:
    """Aggregates independent agent estimates into one collective answer."""

    TRUST_CEILING = 0.5            # diversity above this -> not trustworthy
    TRIM_FRACTION = 0.25           # drop this fraction from each tail

    def __init__(self, *, bus: Optional[EventBus] = None) -> None:
        self._bus = bus
        self._aggregations = 0

    def aggregate(
        self,
        estimates: Sequence[Estimate],
        *,
        method: str = "trimmed_weighted",
        weight_of: Optional[Callable[[str], float]] = None,
    ) -> HiveResult:
        """
        Aggregate estimates into one value.

        ``method`` is "mean", "weighted", or "trimmed_weighted".
        ``weight_of`` overrides per-agent weights (e.g. reputation × the
        task's capability dimension); Estimate.weight is the fallback.
        """
        if not estimates:
            raise AggregationError("cannot aggregate zero estimates")

        pairs = [
            (e.value, weight_of(e.agent_id) if weight_of else e.weight)
            for e in estimates
        ]
        pairs = [(v, max(w, 0.0)) for v, w in pairs]
        used = list(pairs)

        if method == "trimmed_weighted" and len(used) >= 4:
            ordered = sorted(used, key=lambda p: p[0])
            cut = max(1, int(len(ordered) * self.TRIM_FRACTION))
            used = ordered[cut:-cut] or ordered
        elif method not in ("mean", "weighted", "trimmed_weighted"):
            raise AggregationError(f"unknown method {method!r}")

        if method == "mean":
            value = sum(v for v, _ in used) / len(used)
        else:
            total_w = sum(w for _, w in used)
            value = (
                sum(v * w for v, w in used) / total_w
                if total_w > 0
                else sum(v for v, _ in used) / len(used)
            )

        values = [v for v, _ in used]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / max(len(values) - 1, 1)
        diversity = (variance ** 0.5 / abs(mean)) if mean != 0 else float("inf")
        result = HiveResult(
            value=value,
            method=method,
            n_estimates=len(estimates),
            n_used=len(used),
            diversity=diversity,
            spread=max(values) - min(values),
            trustworthy=diversity <= self.TRUST_CEILING,
        )

        self._aggregations += 1
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="swarm.hive.aggregated",
                    payload={
                        "method": method,
                        "value": round(value, 6),
                        "n_estimates": result.n_estimates,
                        "n_used": result.n_used,
                        "diversity": round(diversity, 4),
                        "trustworthy": result.trustworthy,
                    },
                    correlation_id=f"hive_{self._aggregations}",
                )
            )
        return result

    def stats(self) -> Dict[str, Any]:
        return {"aggregations": self._aggregations}
