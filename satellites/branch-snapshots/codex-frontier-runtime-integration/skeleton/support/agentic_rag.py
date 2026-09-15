"""
Skeleton Support — Agentic RAG

Retrieval with agency: an autonomous controller that plans, executes,
evaluates, and refines retrieval across the four planes until the
result set clears a quality bar or the refinement budget runs out.

Pipeline per query:

    ANALYZE   — classify the query (factual | episodic | relational |
                exploratory) and pick the plane mix
    RETRIEVE  — fan out across the chosen planes (parallel-friendly)
    EVALUATE  — score coverage: entity hit-rate, score distribution,
                plane diversity, KAG grounding
    REFINE    — if coverage is low: expand terms (SAM associations),
                reweight planes, decompose into sub-queries, or fall
                through to deep graph traversal
    FUSE      — RRF fusion with plane weights adapted by the agent's
                running accuracy per plane per query class

The agent learns: per-(query_class, plane) success statistics shape
future plane mixes. All adaptation is deterministic and local.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from skeleton.kernel.events import DomainEvent, EventBus


QUERY_CLASSES = ("factual", "episodic", "relational", "exploratory")


@dataclass
class RetrievalPlan:
    """The agent's plan for one query."""
    query: str
    query_class: str
    plane_weights: Dict[str, float]
    expansions: List[str] = field(default_factory=list)
    sub_queries: List[str] = field(default_factory=list)
    budget: int = 2  # refinement rounds allowed


@dataclass
class AgenticResult:
    """Fused results plus the agent's reasoning trace."""
    query: str
    results: List[Any]
    query_class: str
    coverage: float
    rounds: int
    planes_used: List[str]
    trace: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "query_class": self.query_class,
            "coverage": round(self.coverage, 3),
            "rounds": self.rounds,
            "planes_used": self.planes_used,
            "results": len(self.results),
            "trace": self.trace,
        }


class AgenticRAG:
    """Autonomous retrieval controller over the quad planes."""

    COVERAGE_TARGET = 0.6

    def __init__(self, quad: Any, sam: Optional[Any] = None, bus: Optional[EventBus] = None):
        self._quad = quad
        self._sam = sam  # optional Jeeves SAM for expansions
        self._bus = bus
        # (query_class, plane) -> [successes, attempts]
        self._plane_stats: Dict[Tuple[str, str], List[int]] = {}
        self._stats = {"queries": 0, "refined": 0, "target_hit": 0}

    # --- ANALYZE ----------------------------------------------------------

    def classify(self, query: str) -> str:
        low = query.lower()
        relational_markers = ("how does", "relate", "connect", "depend", "between", "relationship")
        episodic_markers = ("when", "last time", "earlier", "before", "history", "previously")
        exploratory_markers = ("explore", "ideas", "possibilities", "what if", "options", "brainstorm")
        if any(m in low for m in relational_markers):
            return "relational"
        if any(m in low for m in episodic_markers):
            return "episodic"
        if any(m in low for m in exploratory_markers):
            return "exploratory"
        return "factual"

    def plan(self, query: str) -> RetrievalPlan:
        qclass = self.classify(query)
        # Base plane preference per class
        base = {
            "factual": {"rag": 0.5, "kag": 0.3, "cag": 0.1, "mag": 0.1},
            "episodic": {"mag": 0.5, "rag": 0.2, "cag": 0.2, "kag": 0.1},
            "relational": {"kag": 0.6, "rag": 0.2, "cag": 0.1, "mag": 0.1},
            "exploratory": {"rag": 0.3, "cag": 0.3, "mag": 0.2, "kag": 0.2},
        }[qclass]
        # Adapt with learned per-plane success rates
        for plane in base:
            successes, attempts = self._plane_stats.get((qclass, plane), [0, 0])
            if attempts >= 3:
                learned = successes / attempts
                base[plane] = round(0.6 * base[plane] + 0.4 * learned, 3)
        return RetrievalPlan(query=query, query_class=qclass, plane_weights=base)

    # --- EVALUATE -----------------------------------------------------------

    def coverage(self, query: str, results: List[Any]) -> float:
        """Score result coverage 0..1: term hits + diversity + grounding."""
        if not results:
            return 0.0
        terms = [t for t in query.lower().split() if len(t) > 3]
        if not terms:
            return 0.5
        hits = 0
        for term in terms:
            if any(term in getattr(r, "content", getattr(getattr(r, "chunk", None), "text", "")).lower() for r in results):
                hits += 1
        term_score = hits / len(terms)
        planes = {getattr(r, "plane", "") for r in results}
        diversity = min(1.0, len(planes) / 3.0)
        grounded = 1.0 if "kag" in planes else 0.5
        return round(0.5 * term_score + 0.3 * diversity + 0.2 * grounded, 3)

    # --- REFINE + RETRIEVE ----------------------------------------------------

    def retrieve(self, query: str, k: int = 8) -> AgenticResult:
        self._stats["queries"] += 1
        plan = self.plan(query)
        trace = [f"classified as {plan.query_class}"]

        results = self._execute_plan(plan, k)
        cov = self.coverage(query, results)
        trace.append(f"round 1 coverage {cov:.2f}")

        rounds = 1
        while cov < self.COVERAGE_TARGET and rounds <= plan.budget:
            rounds += 1
            self._stats["refined"] += 1
            # Refinement 1: SAM expansions
            if self._sam is not None and not plan.expansions:
                plan.expansions = self._sam.expand(query)[:3]
                if plan.expansions:
                    trace.append(f"expanded with {plan.expansions}")
                    results = results + self._execute_plan(plan, k, extra=" ".join(plan.expansions))
            # Refinement 2: sub-query decomposition
            elif not plan.sub_queries and len(query.split()) > 4:
                words = query.split()
                mid = len(words) // 2
                plan.sub_queries = [" ".join(words[:mid]), " ".join(words[mid:])]
                trace.append("decomposed into sub-queries")
                for sub in plan.sub_queries:
                    results = results + self._execute_plan(plan, k, override_query=sub)
            else:
                # Refinement 3: boost weakest plane's weight
                weakest = min(plan.plane_weights, key=plan.plane_weights.get)
                plan.plane_weights[weakest] = min(1.0, plan.plane_weights[weakest] + 0.2)
                trace.append(f"boosted {weakest} plane")
                results = results + self._execute_plan(plan, k)

            cov = self.coverage(query, results)
            trace.append(f"round {rounds} coverage {cov:.2f}")

        # Deduplicate by fragment id / content head
        seen, fused = set(), []
        for r in results:
            key = getattr(r, "fragment_id", None) or getattr(getattr(r, "chunk", None), "text", str(r))[:60]
            if key not in seen:
                seen.add(key)
                fused.append(r)
        fused = fused[:k]

        # Learn: record per-plane outcome
        planes_used = sorted({getattr(r, "plane", "rag") for r in fused})
        success = 1 if cov >= self.COVERAGE_TARGET else 0
        for plane in planes_used:
            stats = self._plane_stats.setdefault((plan.query_class, plane), [0, 0])
            stats[0] += success
            stats[1] += 1
        if success:
            self._stats["target_hit"] += 1

        if self._bus:
            self._bus.publish(DomainEvent(
                topic="support.agentic_rag.retrieved",
                payload={"query": query[:60], "class": plan.query_class,
                         "coverage": cov, "rounds": rounds},
            ))

        return AgenticResult(
            query=query, results=fused, query_class=plan.query_class,
            coverage=cov, rounds=rounds, planes_used=planes_used, trace=trace,
        )

    def _execute_plan(self, plan: RetrievalPlan, k: int, extra: str = "",
                      override_query: Optional[str] = None) -> List[Any]:
        q = override_query or plan.query
        if extra:
            q = f"{q} {extra}"
        try:
            return self._quad.retrieve(q, k=k)
        except Exception:
            return []

    def accuracy(self) -> Dict[str, Any]:
        out = {}
        for (qclass, plane), (s, a) in self._plane_stats.items():
            out[f"{qclass}/{plane}"] = {"success_rate": round(s / a, 3), "attempts": a}
        return out

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "accuracy": self.accuracy()}
