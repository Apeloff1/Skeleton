"""Resilience metrics — counters for threat categories and levels.

The fortress decides; this counts. Trip counters per threat report,
summaries by category and level, and a running total for dashboards.
"""

from __future__ import annotations

from typing import Any, Dict

from skeleton.resilience.types import ThreatReport


class ThreatMetrics:
    """Aggregate counters over incoming threat reports."""

    def __init__(self) -> None:
        self._total = 0
        self._by_level: Dict[str, int] = {}
        self._by_category: Dict[str, int] = {}

    def record(self, report: ThreatReport) -> None:
        self._total += 1
        level_key = report.level.value if hasattr(report.level, "value") else str(report.level)
        category_key = (
            report.category.value if hasattr(report.category, "value") else str(report.category)
        )
        self._by_level[level_key] = self._by_level.get(level_key, 0) + 1
        self._by_category[category_key] = self._by_category.get(category_key, 0) + 1

    def report(self) -> Dict[str, Any]:
        return {
            "total": self._total,
            "by_level": dict(self._by_level),
            "by_category": dict(self._by_category),
        }

    def reset(self) -> None:
        self._total = 0
        self._by_level.clear()
        self._by_category.clear()
