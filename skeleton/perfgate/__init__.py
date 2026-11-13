"""GF-M perf gates: soak harness + perf budgets + baseline regression compare.

Pure stdlib. Workloads are plain callables so the harness can drive the
GameForge walk (``skeleton.forge.walk_cli.walk_once``) or any forge E2E step.
"""
from .stats import Summary, summarize, percentile
from .budget import Budget, BudgetSet, BudgetViolation, load_budgets
from .baseline import Baseline, RegressionReport, compare, load_baseline, save_baseline
from .soak import SoakConfig, SoakResult, run_soak

__all__ = [
    "Summary", "summarize", "percentile",
    "Budget", "BudgetSet", "BudgetViolation", "load_budgets",
    "Baseline", "RegressionReport", "compare", "load_baseline", "save_baseline",
    "SoakConfig", "SoakResult", "run_soak",
]
