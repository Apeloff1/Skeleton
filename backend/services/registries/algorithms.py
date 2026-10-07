"""
services/registries/algorithms.py — ALGORITHM_REGISTRY.

Extracted from server.py (Feb 2026 Phase-8). Pure data: state-of-the-art
algorithm catalogue grouped by category.
"""
from __future__ import annotations


ALGORITHM_REGISTRY = {
    # Parsing Algorithms
    "parsing": {
        "ll1": {"name": "LL(1)", "type": "top_down", "complexity": "O(n)", "description": "Predictive parsing with 1 lookahead"},
        "lr1": {"name": "LR(1)", "type": "bottom_up", "complexity": "O(n)", "description": "Canonical LR parsing"},
        "lalr1": {"name": "LALR(1)", "type": "bottom_up", "complexity": "O(n)", "description": "Look-Ahead LR, used by yacc/bison"},
        "glr": {"name": "GLR", "type": "generalized", "complexity": "O(n³) worst", "description": "Generalized LR for ambiguous grammars"},
        "earley": {"name": "Earley", "type": "chart", "complexity": "O(n³)", "description": "Chart parsing for all CFGs"},
        "peg": {"name": "PEG", "type": "packrat", "complexity": "O(n)", "description": "Parsing Expression Grammar with memoization"},
        "gll": {"name": "GLL", "type": "generalized", "complexity": "O(n³)", "description": "Generalized LL parsing"},
        "pratt": {"name": "Pratt Parser", "type": "operator_precedence", "complexity": "O(n)", "description": "Top-down operator precedence"},
    },
    # Optimization Algorithms
    "optimization": {
        "ssa": {"name": "SSA Construction", "complexity": "O(n)", "description": "Static Single Assignment form conversion"},
        "dominators": {"name": "Dominance", "complexity": "O(n²)", "description": "Dominator tree construction"},
        "loop_detection": {"name": "Loop Analysis", "complexity": "O(n)", "description": "Natural loop detection"},
        "constant_propagation": {"name": "Sparse Conditional CP", "complexity": "O(n)", "description": "Constant propagation with control flow"},
        "dead_code_elimination": {"name": "DCE", "complexity": "O(n)", "description": "Dead code elimination"},
        "gcse": {"name": "GCSE", "complexity": "O(n²)", "description": "Global common subexpression elimination"},
        "licm": {"name": "LICM", "complexity": "O(n)", "description": "Loop invariant code motion"},
        "strength_reduction": {"name": "Strength Reduction", "complexity": "O(n)", "description": "Replace expensive ops with cheaper ones"},
        "induction_variable": {"name": "IV Optimization", "complexity": "O(n)", "description": "Induction variable optimization"},
        "vectorization": {"name": "Auto-Vectorization", "complexity": "O(n²)", "description": "SIMD instruction generation"},
        "polyhedral": {"name": "Polyhedral Model", "complexity": "exponential", "description": "Loop nest optimization"},
    },
    # Register Allocation
    "register_allocation": {
        "linear_scan": {"name": "Linear Scan", "complexity": "O(n log n)", "description": "Fast allocation via live intervals"},
        "graph_coloring": {"name": "Graph Coloring", "complexity": "NP-complete", "description": "Optimal allocation via interference graph"},
        "chaitin_briggs": {"name": "Chaitin-Briggs", "complexity": "O(n²)", "description": "Iterative graph coloring with spilling"},
        "ssa_based": {"name": "SSA-based", "complexity": "O(n)", "description": "Register allocation on SSA form"},
        "pbqp": {"name": "PBQP", "complexity": "O(n²)", "description": "Partitioned Boolean Quadratic Programming"},
    },
    # Instruction Selection
    "instruction_selection": {
        "maximal_munch": {"name": "Maximal Munch", "complexity": "O(n)", "description": "Greedy tree covering"},
        "burg": {"name": "BURG", "complexity": "O(n)", "description": "Bottom-up rewrite system"},
        "iburg": {"name": "IBURG", "complexity": "O(n)", "description": "Interpreted BURG"},
        "superoptimization": {"name": "Superoptimization", "complexity": "exponential", "description": "Exhaustive search for optimal code"},
    },
    # Garbage Collection
    "garbage_collection": {
        "mark_sweep": {"name": "Mark-Sweep", "complexity": "O(live)", "description": "Classic tracing GC"},
        "mark_compact": {"name": "Mark-Compact", "complexity": "O(heap)", "description": "Compacting tracing GC"},
        "copying": {"name": "Copying", "complexity": "O(live)", "description": "Semi-space copying collector"},
        "generational": {"name": "Generational", "complexity": "O(young)", "description": "Age-based collection"},
        "incremental": {"name": "Incremental", "complexity": "O(n)", "description": "Pauseless incremental GC"},
        "concurrent": {"name": "Concurrent", "complexity": "O(n)", "description": "Concurrent marking GC"},
        "reference_counting": {"name": "Reference Counting", "complexity": "O(1)", "description": "Immediate reclamation"},
    },
}


__all__ = ["ALGORITHM_REGISTRY"]
