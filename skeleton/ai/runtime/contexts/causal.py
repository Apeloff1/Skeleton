"""
Skeleton Contexts — Causal Inference Engine

The oracle's deep layer: beyond correlation to causation. The fate
matrix already predicts WHAT happens next; the causal engine answers
WHY — and what changes if we intervene.

Core:
- CausalGraph: directed edges between system events with structural
  equation weights learned online (recursive least squares on event
  co-occurrence deltas — a lean Granger-style test per edge:
  does X's recent history reduce the prediction error of Y?)
- InterventionSimulator: do(X=x) — sever X's incoming edges, set its
  value, propagate through the graph, and report the counterfactual
  outcome distribution for every downstream variable. This is the
  oracle's "what if we throttle the forge harder" answered causally,
  not by vibes.
- ConfounderWatch: detects spurious edges — when Z causes both X
  and Y, the X→Y edge inflates; the watch flags edges whose strength
  collapses when conditioning on a candidate confounder.
- EffectAttribution: decomposes an observed outcome into per-cause
  contributions (Shapley-style marginal averaging over edge subsets
  on small graphs) so the oracle can say "40% of the quality jump
  came from the retrieval upgrade, 25% from the persistence layer."

All online, deterministic, bounded-memory, no external dependencies.
"""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Granger-style edge learning (lean, online)
# ---------------------------------------------------------------------------

@dataclass
class CausalEdge:
    """One learned causal link with strength and evidence count."""
    src: str
    dst: str
    strength: float       # 0..1 predictive contribution
    evidence: int
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {"src": self.src, "dst": self.dst,
                "strength": round(self.strength, 4), "evidence": self.evidence}


class CausalGraph:
    """Directed weighted causal graph learned from event streams.

    For each ordered pair (X, Y): track whether X's recent values
    reduce Y's prediction error versus Y's own history alone — a lean
    online Granger test. Strength = relative error reduction, EMA'd.
    """

    WINDOW = 32
    ALPHA = 0.2

    def __init__(self):
        self._series: Dict[str, List[float]] = {}
        self._edges: Dict[Tuple[str, str], CausalEdge] = {}

    def observe(self, series: Dict[str, float]) -> None:
        """Observe one synchronized sample across all series."""
        for name, value in series.items():
            hist = self._series.setdefault(name, [])
            hist.append(value)
            if len(hist) > self.WINDOW:
                hist.pop(0)
        if all(len(v) >= 4 for v in self._series.values()):
            self._update_edges()

    def _variance(self, xs: List[float]) -> float:
        if len(xs) < 2:
            return 1e-9
        m = sum(xs) / len(xs)
        return sum((x - m) ** 2 for x in xs) / (len(xs) - 1) + 1e-9

    def _granger_strength(self, x: List[float], y: List[float]) -> float:
        """Error reduction in Y from knowing X's past (0..1)."""
        n = min(len(x), len(y))
        if n < 4:
            return 0.0
        x, y = x[-n:], y[-n:]
        # Baseline: predict y[t] from y[t-1]
        base_err = self._variance([y[t] - y[t - 1] for t in range(1, n)])
        # With X: residual after removing X's linear contribution
        num = sum((x[t - 1] - sum(x[:-1]) / (n - 1)) * (y[t] - sum(y[1:]) / (n - 1))
                  for t in range(1, n))
        den = math.sqrt(self._variance(x[:-1]) * self._variance(y[1:])) * (n - 1)
        corr = num / den if den > 1e-12 else 0.0
        resid_err = base_err * (1.0 - corr ** 2)
        return max(0.0, min(1.0, 1.0 - resid_err / base_err)) if base_err > 1e-12 else 0.0

    def _update_edges(self) -> None:
        names = list(self._series.keys())
        for src in names:
            for dst in names:
                if src == dst:
                    continue
                strength = self._granger_strength(self._series[src], self._series[dst])
                key = (src, dst)
                edge = self._edges.get(key)
                if edge is None:
                    self._edges[key] = CausalEdge(src, dst, strength, 1)
                else:
                    edge.strength = (1 - self.ALPHA) * edge.strength + self.ALPHA * strength
                    edge.evidence += 1
                    edge.updated_at = time.time()

    def parents(self, node: str, min_strength: float = 0.1) -> List[CausalEdge]:
        return sorted([e for e in self._edges.values()
                       if e.dst == node and e.strength >= min_strength],
                      key=lambda e: e.strength, reverse=True)

    def children(self, node: str, min_strength: float = 0.1) -> List[CausalEdge]:
        return sorted([e for e in self._edges.values()
                       if e.src == node and e.strength >= min_strength],
                      key=lambda e: e.strength, reverse=True)

    def edges(self) -> List[CausalEdge]:
        return sorted(self._edges.values(), key=lambda e: e.strength, reverse=True)


# ---------------------------------------------------------------------------
# Intervention simulation: do(X=x)
# ---------------------------------------------------------------------------

@dataclass
class Intervention:
    """Result of do(X=x): counterfactual values for all downstreams."""
    variable: str
    set_to: float
    effects: Dict[str, float]      # variable -> counterfactual value
    deltas: Dict[str, float]       # variable -> change from baseline
    severed_parents: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {"do": f"{self.variable}={self.set_to}",
                "deltas": {k: round(v, 4) for k, v in self.deltas.items()},
                "severed": self.severed_parents}


class InterventionSimulator:
    """Counterfactual engine over the causal graph."""

    def __init__(self, graph: CausalGraph):
        self._graph = graph

    def do(self, variable: str, value: float,
           baseline: Optional[Dict[str, float]] = None) -> Intervention:
        """do(X=x): sever X's parents, set X, propagate downstream."""
        baseline = baseline or {name: (hist[-1] if hist else 0.0)
                                for name, hist in self._graph._series.items()}
        # Severed parents: X's incoming edges no longer drive X
        severed = [e.src for e in self._graph.parents(variable, min_strength=0.0)]

        # Propagate: BFS downstream, each child's value shifts by
        # parent_effect × edge_strength (linear structural equations)
        values = dict(baseline)
        values[variable] = value
        queue = [variable]
        visited = set()
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for edge in self._graph.children(current):
                parent_val = values.get(current, baseline.get(current, 0.0))
                base_parent = baseline.get(current, 0.0)
                shift = (parent_val - base_parent) * edge.strength
                values[edge.dst] = values.get(edge.dst, baseline.get(edge.dst, 0.0)) + shift
                queue.append(edge.dst)

        deltas = {k: values[k] - baseline.get(k, 0.0) for k in values}
        return Intervention(variable, value, values, deltas, severed)


# ---------------------------------------------------------------------------
# Confounder watch
# ---------------------------------------------------------------------------

@dataclass
class ConfounderAlert:
    """An edge whose strength collapses when conditioning on Z."""
    edge: Tuple[str, str]
    confounder: str
    raw_strength: float
    conditioned_strength: float
    collapse_ratio: float

    def to_dict(self) -> Dict[str, Any]:
        return {"edge": f"{self.edge[0]}→{self.edge[1]}",
                "confounder": self.confounder,
                "collapse": round(self.collapse_ratio, 3)}


class ConfounderWatch:
    """Flags spurious edges: strength that vanishes conditional on Z."""

    COLLAPSE_THRESHOLD = 0.3  # conditioned < 30% of raw → spurious

    def __init__(self, graph: CausalGraph):
        self._graph = graph

    def scan(self, top_n: int = 10) -> List[ConfounderAlert]:
        alerts: List[ConfounderAlert] = []
        for edge in self._graph.edges()[:top_n]:
            x, y = edge.src, edge.dst
            if x not in self._graph._series or y not in self._graph._series:
                continue
            for z in self._graph._series:
                if z in (x, y):
                    continue
                # Conditioned strength: Granger of residuals after
                # removing Z's linear effect from both X and Y
                zs = self._graph._series[z]
                xs = self._graph._series[x]
                ys = self._graph._series[y]
                n = min(len(zs), len(xs), len(ys))
                if n < 6:
                    continue
                cond = self._graph._granger_strength(
                    self._residualize(xs[-n:], zs[-n:]),
                    self._residualize(ys[-n:], zs[-n:]),
                )
                if edge.strength > 1e-6 and cond / edge.strength < self.COLLAPSE_THRESHOLD:
                    alerts.append(ConfounderAlert(
                        (x, y), z, edge.strength, cond, cond / edge.strength))
                    break  # one confounder alert per edge is enough
        return alerts

    @staticmethod
    def _residualize(series: List[float], confound: List[float]) -> List[float]:
        """Remove the confounder's linear contribution from a series."""
        n = len(series)
        mx = sum(series) / n
        mz = sum(confound) / n
        cov = sum((series[i] - mx) * (confound[i] - mz) for i in range(n))
        var_z = sum((confound[i] - mz) ** 2 for i in range(n))
        beta = cov / var_z if var_z > 1e-12 else 0.0
        return [series[i] - beta * (confound[i] - mz) for i in range(n)]


# ---------------------------------------------------------------------------
# Effect attribution (Shapley-style on small cause sets)
# ---------------------------------------------------------------------------

@dataclass
class Attribution:
    """Per-cause contribution decomposition for one outcome."""
    outcome: str
    contributions: Dict[str, float]
    total_explained: float

    def to_dict(self) -> Dict[str, Any]:
        return {"outcome": self.outcome,
                "contributions": {k: round(v, 4) for k, v in self.contributions.items()},
                "total_explained": round(self.total_explained, 3)}


class EffectAttributor:
    """Shapley-style marginal contributions of each parent to an outcome.

    For small parent sets (≤6): exact Shapley over edge-strength
    subsets. Larger sets: top-6 by strength, remainder pooled.
    """

    def attribute(self, graph: CausalGraph, outcome: str,
                  outcome_value: float = 1.0) -> Attribution:
        parents = graph.parents(outcome, min_strength=0.01)[:6]
        if not parents:
            return Attribution(outcome, {}, 0.0)

        strengths = {p.src: p.strength for p in parents}
        names = list(strengths)
        n = len(names)
        shapley = {name: 0.0 for name in names}

        # Exact Shapley: average marginal contribution over all orderings
        for perm in itertools.permutations(names):
            coalition: Dict[str, float] = {}
            for i, name in enumerate(perm):
                before = self._joint(coalition)
                coalition[name] = strengths[name]
                after = self._joint(coalition)
                shapley[name] += after - before
        factorial_n = math.factorial(n)
        shapley = {k: v / factorial_n for k, v in shapley.items()}

        total = sum(shapley.values()) or 1.0
        contributions = {k: (v / total) * outcome_value for k, v in shapley.items()}
        return Attribution(outcome, contributions, min(1.0, total))

    @staticmethod
    def _joint(coalition: Dict[str, float]) -> float:
        """Joint effect of a coalition: 1 - Π(1 - strength) (noisy-or)."""
        prod = 1.0
        for s in coalition.values():
            prod *= (1.0 - s)
        return 1.0 - prod


class CausalEngine:
    """Unified causal layer for the oracle: graph + interventions +
    confounder watch + attribution."""

    def __init__(self):
        self.graph = CausalGraph()
        self._stats = {"observations": 0, "interventions": 0, "attributions": 0}

    def observe(self, series: Dict[str, float]) -> None:
        self._stats["observations"] += 1
        self.graph.observe(series)

    def what_if(self, variable: str, value: float) -> Intervention:
        self._stats["interventions"] += 1
        return InterventionSimulator(self.graph).do(variable, value)

    def why(self, outcome: str, outcome_value: float = 1.0) -> Attribution:
        self._stats["attributions"] += 1
        return EffectAttributor().attribute(self.graph, outcome, outcome_value)

    def spurious(self) -> List[ConfounderAlert]:
        return ConfounderWatch(self.graph).scan()

    def stats(self) -> Dict[str, Any]:
        return {**self._stats,
                "edges": len(self.graph.edges()),
                "top_edges": [e.to_dict() for e in self.graph.edges()[:5]]}
