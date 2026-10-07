from __future__ import annotations
"""
SOTA mathematical tool registry for GameForge Math Exocortex.
Certainty-first: symbolic exactness, formal proof, deterministic mechanics.
"""

from typing import Any, Dict, List


SOTA_MATH_TOOL_LIST: List[Dict[str, Any]] = [
    # Tier 1 — Numerical exact-ish / rational
    {
        "id": "safe_calculator",
        "tier": "primary",
        "name": "Safe Arithmetic Calculator",
        "capability": "AST-safe evaluation of arithmetic and elementary functions",
        "certainty": "deterministic",
        "status": "implemented",
    },
    {
        "id": "spreadsheet_grid",
        "tier": "primary",
        "name": "Spreadsheet Grid",
        "capability": "Cell store with SUM ranges and formula references",
        "certainty": "deterministic",
        "status": "implemented",
    },
    {
        "id": "rational_weights_scale",
        "tier": "advanced",
        "name": "Virtual Weights / Counterweights / Scales",
        "capability": "Exact Fraction lever moments and balance equations",
        "certainty": "exact_rational",
        "status": "implemented",
    },
    {
        "id": "gear_pulley_statics",
        "tier": "advanced",
        "name": "Gear Ratios & Ideal Pulley Advantage",
        "capability": "Exact mechanical advantage and gear ratios",
        "certainty": "exact_rational",
        "status": "implemented",
    },
    # Tier 2 — Symbolic
    {
        "id": "sympy_workspace",
        "tier": "secondary",
        "name": "SymPy Symbolic Workspace",
        "capability": "Exact algebra, calculus, matrices, series, limits",
        "certainty": "symbolic_exact",
        "status": "implemented",
        "init": "gameforge.math_exocortex.sympy_init.initialize_sympy_workspace",
    },
    {
        "id": "sympy_simplify_expand_factor",
        "tier": "secondary",
        "name": "Algebraic Simplification Suite",
        "capability": "simplify / expand / factor / cancel / apart / trigsimp",
        "certainty": "symbolic_exact",
        "status": "implemented",
    },
    {
        "id": "sympy_diff_integrate",
        "tier": "secondary",
        "name": "Exact Calculus",
        "capability": "Differentiation and symbolic integration",
        "certainty": "symbolic_exact",
        "status": "implemented",
    },
    {
        "id": "sympy_solve_dsolve",
        "tier": "secondary",
        "name": "Equation Solvers",
        "capability": "Algebraic solve and ODE dsolve",
        "certainty": "symbolic_exact",
        "status": "implemented",
    },
    {
        "id": "sympy_matrix",
        "tier": "secondary",
        "name": "Exact Linear Algebra",
        "capability": "Matrix det, rank, symbolic entries",
        "certainty": "symbolic_exact",
        "status": "implemented",
    },
    # Tier 3 — Distributed deterministic sharding
    {
        "id": "pow_mapreduce",
        "tier": "tertiary",
        "name": "Emulated Bitcoin PoW MapReduce",
        "capability": "Shard large numerical problems, mine blocks, merkle reassembly",
        "certainty": "deterministic_reproducible",
        "status": "implemented",
    },
    {
        "id": "pow_miner_logs",
        "tier": "tertiary",
        "name": "Shard Miner + Block Logs",
        "capability": "Full audit of nonce, hash, work_ms, assemble",
        "certainty": "auditable",
        "status": "implemented",
    },
    # Formal certainty
    {
        "id": "lean4_verifier",
        "tier": "formal",
        "name": "Lean 4 Formal Verification",
        "capability": "Proof obligations, tactic injection, proved|sorry|failed status",
        "certainty": "machine_checked_when_proved",
        "status": "implemented",
    },
    {
        "id": "coq_bridge",
        "tier": "formal",
        "name": "Coq Bridge",
        "capability": "Optional alternate prover interface",
        "certainty": "machine_checked_when_connected",
        "status": "interface",
    },
    # Structure / geometry / viz (deterministic outputs)
    {
        "id": "networkx_critical_path",
        "tier": "advanced",
        "name": "DAG Critical Path (NetworkX)",
        "capability": "Longest path on task dependency DAGs",
        "certainty": "graph_exact_on_dag",
        "status": "implemented",
    },
    {
        "id": "matplotlib_charts",
        "tier": "advanced",
        "name": "Deterministic Chart Export",
        "capability": "Line/bar figures for exact series display",
        "certainty": "reproducible_render",
        "status": "implemented",
    },
    {
        "id": "budget_ledger",
        "tier": "advanced",
        "name": "Exact Budget Ledger",
        "capability": "Income/expense/limits with utilization ratios",
        "certainty": "deterministic",
        "status": "implemented",
    },
    # Explicitly NOT used for decisions requiring certainty
    {
        "id": "probability_engines",
        "tier": "excluded",
        "name": "Bayesian / MCMC / Probability Clouds",
        "capability": "Uncertainty forecasting",
        "certainty": "probabilistic — excluded from certainty path",
        "status": "disabled_for_certainty_mode",
    },
]


def sota_tool_list(*, include_excluded: bool = False) -> List[Dict[str, Any]]:
    if include_excluded:
        return list(SOTA_MATH_TOOL_LIST)
    return [t for t in SOTA_MATH_TOOL_LIST if t.get("status") != "disabled_for_certainty_mode"]


def sota_summary() -> Dict[str, Any]:
    tools = sota_tool_list(include_excluded=True)
    by_tier: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for t in tools:
        by_tier[t["tier"]] = by_tier.get(t["tier"], 0) + 1
        by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    return {
        "count": len(tools),
        "by_tier": by_tier,
        "by_status": by_status,
        "certainty_policy": "Prefer exact rational, symbolic, and machine-checked proofs. Probability engines disabled in certainty mode.",
        "tools": sota_tool_list(include_excluded=False),
    }
