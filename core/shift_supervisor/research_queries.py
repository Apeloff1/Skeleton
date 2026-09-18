from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ResearchQuery:
    topic: str
    query: str
    purpose: str
    priority: int = 50


def derive_queries(project_context: dict[str, Any], *, limit: int = 20) -> list[ResearchQuery]:
    """Create deterministic baseline research questions before model planning."""
    repo = str(project_context.get("repository", project_context.get("repo", "project")))
    candidates = [
        ResearchQuery("ci", f"{repo} current failing CI checks and root causes", "unblock validated delivery", 100),
        ResearchQuery("backlog", f"{repo} highest-impact open backlog and dependencies", "prioritize executable work", 90),
        ResearchQuery("security", f"{repo} unresolved security findings and dependency alerts", "reduce known risk", 90),
        ResearchQuery("tests", f"{repo} weak or missing regression coverage", "prevent regressions", 80),
        ResearchQuery("architecture", f"{repo} integration boundaries and duplicated subsystems", "avoid parallel incompatible systems", 70),
        ResearchQuery("performance", f"{repo} known performance bottlenecks and benchmarks", "target evidence-backed optimization", 60),
        ResearchQuery("docs", f"{repo} stale operational documentation", "keep autonomous workers aligned", 40),
    ]
    return sorted(candidates, key=lambda q: -q.priority)[: max(0, limit)]
