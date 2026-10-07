from __future__ import annotations
"""
Advanced SOTA tools: visualization, NetworkX critical path, Bayesian stubs, budget.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import os
import logging
import math

logger = logging.getLogger("gameforge.math.advanced")


# ----- Budget ---------------------------------------------------------------

@dataclass
class BudgetLine:
    category: str
    amount: float
    currency: str = "NOK"
    note: str = ""


class BudgetSystem:
    def __init__(self, currency: str = "NOK"):
        self.currency = currency
        self.income: List[BudgetLine] = []
        self.expenses: List[BudgetLine] = []
        self.limits: Dict[str, float] = {}

    def add_income(self, category: str, amount: float, note: str = ""):
        self.income.append(BudgetLine(category, amount, self.currency, note))

    def add_expense(self, category: str, amount: float, note: str = ""):
        self.expenses.append(BudgetLine(category, amount, self.currency, note))

    def set_limit(self, category: str, amount: float):
        self.limits[category] = amount

    def summary(self) -> Dict[str, Any]:
        inc = sum(x.amount for x in self.income)
        exp = sum(x.amount for x in self.expenses)
        by_cat: Dict[str, float] = {}
        for e in self.expenses:
            by_cat[e.category] = by_cat.get(e.category, 0.0) + e.amount
        util = {}
        for cat, lim in self.limits.items():
            used = by_cat.get(cat, 0.0)
            util[cat] = {"used": used, "limit": lim, "utilization": (used / lim) if lim else 0.0}
        overall_util = (exp / inc) if inc else 0.0
        return {
            "currency": self.currency,
            "income_total": inc,
            "expense_total": exp,
            "balance": inc - exp,
            "by_category": by_cat,
            "limits": util,
            "utilization": overall_util,
        }


# ----- Visualization --------------------------------------------------------

class ChartService:
    def __init__(self):
        base = Path(os.getenv("GAMEFORGE_DATA_DIR", "/tmp/gameforge_data"))
        self.out = base / "charts"
        self.out.mkdir(parents=True, exist_ok=True)
        self._mpl = None
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt

            self._mpl = plt
        except ImportError:
            logger.warning("matplotlib unavailable")

    @property
    def available(self) -> bool:
        return self._mpl is not None

    def line(self, xs: List[float], ys: List[float], title: str = "line", name: str = "line.png") -> Dict[str, Any]:
        if not self._mpl:
            return {"ok": False, "error": "matplotlib_unavailable"}
        plt = self._mpl
        fig, ax = plt.subplots()
        ax.plot(xs, ys)
        ax.set_title(title)
        path = self.out / name
        fig.savefig(path)
        plt.close(fig)
        return {"ok": True, "path": str(path)}

    def bar(self, labels: List[str], values: List[float], title: str = "bar", name: str = "bar.png") -> Dict[str, Any]:
        if not self._mpl:
            return {"ok": False, "error": "matplotlib_unavailable"}
        plt = self._mpl
        fig, ax = plt.subplots()
        ax.bar(labels, values)
        ax.set_title(title)
        path = self.out / name
        fig.savefig(path)
        plt.close(fig)
        return {"ok": True, "path": str(path)}


# ----- NetworkX critical path -----------------------------------------------

class DependencyGraph:
    def __init__(self):
        self._nx = None
        try:
            import networkx as nx

            self._nx = nx
        except ImportError:
            logger.warning("networkx unavailable")
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Tuple[str, str]] = []

    @property
    def available(self) -> bool:
        return self._nx is not None

    def add_task(self, task_id: str, duration_days: float = 1.0, **meta):
        self.nodes[task_id] = {"duration": duration_days, **meta}

    def add_dep(self, before: str, after: str):
        self.edges.append((before, after))

    def critical_path(self) -> Dict[str, Any]:
        if not self._nx:
            # fallback: longest duration chain naive
            return {"ok": False, "error": "networkx_unavailable", "fallback_total": sum(n["duration"] for n in self.nodes.values())}
        nx = self._nx
        G = nx.DiGraph()
        for tid, meta in self.nodes.items():
            G.add_node(tid, **meta)
        for a, b in self.edges:
            G.add_edge(a, b)
        if not nx.is_directed_acyclic_graph(G):
            return {"ok": False, "error": "graph_has_cycles"}
        # longest path by duration
        try:
            path = nx.dag_longest_path(G, weight="duration")
            length = nx.dag_longest_path_length(G, weight="duration")
            return {"ok": True, "critical_path": path, "total_days": length}
        except Exception as e:
            return {"ok": False, "error": str(e)}


# ----- Bayesian (lightweight without PyMC dependency) -----------------------

class BayesianForecaster:
    """
    Simple Beta-Binomial / Gaussian uncertainty without requiring PyMC.
    Interface-compatible with richer backends later.
    """

    def project_completion(
        self,
        progress_pct: float,
        days_elapsed: float,
        historical_daily_rates: Optional[List[float]] = None,
        weather_penalty: float = 0.0,
        energy: float = 0.55,
    ) -> Dict[str, Any]:
        rates = historical_daily_rates or [max(0.5, progress_pct / max(1.0, days_elapsed))]
        mean_rate = sum(rates) / len(rates)
        # adjust
        mean_rate *= 0.7 + 0.6 * energy
        mean_rate *= max(0.3, 1.0 - weather_penalty)
        remaining = max(0.0, 100.0 - progress_pct)
        if mean_rate <= 1e-6:
            return {"ok": True, "expected_days": None, "p50": None, "p80": None, "note": "rate_too_low"}
        expected = remaining / mean_rate
        # crude spread
        vol = statistics_pstdev(rates) if len(rates) > 1 else mean_rate * 0.2
        p50 = expected
        p80 = expected * (1.0 + min(1.0, vol / max(mean_rate, 1e-6)))
        return {
            "ok": True,
            "expected_days": round(expected, 2),
            "p50_days": round(p50, 2),
            "p80_days": round(p80, 2),
            "mean_daily_rate_pct": round(mean_rate, 3),
            "weather_penalty": weather_penalty,
        }


def statistics_pstdev(xs: List[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


# ----- Formal verification interface (stub for Lean/Coq) --------------------

class FormalVerificationBridge:
    """
    Interface for Lean 4 / Coq. Returns structured obligations until binary is wired.
    """

    def __init__(self):
        self.available_backend = None  # 'lean4' | 'coq' | None

    def prove_obligation(self, statement: str, context: Optional[str] = None) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": "not_connected",
            "statement": statement,
            "hint": "Install Lean 4 or Coq and set GAMEFORGE_LEAN_PATH / GAMEFORGE_COQ_PATH",
            "skeleton": f"theorem goal : {statement} := by\n  sorry",
        }
