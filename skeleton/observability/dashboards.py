"""Dashboard aggregation — fold metrics, health, and alerts into one view.

Operators look at one screen; this aggregates the MetricsRegistry,
HealthRegistry health probe outcome, and AlertingEngine state into a
single snapshot the UI renders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from skeleton.kernel.errors import KernelError


class DashboardError(KernelError):
    code = "OBS.DASHBOARD"


@dataclass
class Widget:
    name: str
    kind: str  # "metric" | "health" | "alert"
    payload: Dict[str, Any] = field(default_factory=dict)


class Dashboard:
    """Collects named widgets and snapshots them."""

    def __init__(self) -> None:
        self._widgets: List[Widget] = []

    def add(self, widget: Widget) -> None:
        self._widgets.append(widget)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "widgets": [
                {"name": w.name, "kind": w.kind, "payload": w.payload}
                for w in self._widgets
            ]
        }


def aggregate(
    *, metrics: Optional[Any] = None,
    health: Optional[Any] = None,
    alerts: Optional[Any] = None,
) -> Dashboard:
    """Aggregate common observability sources into one Dashboard."""
    dashboard = Dashboard()
    if metrics is not None and hasattr(metrics, "snapshot"):
        try:
            dashboard.add(
                Widget(name="metrics", kind="metric", payload=metrics.snapshot())
            )
        except Exception:
            pass
    if health is not None:
        try:
            report = health.readiness() if hasattr(health, "readiness") else {}
            dashboard.add(Widget(name="health", kind="health", payload=report))
        except Exception:
            pass
    if alerts is not None:
        try:
            status = alerts.status() if hasattr(alerts, "status") else {}
            dashboard.add(Widget(name="alerts", kind="alert", payload=status))
        except Exception:
            pass
    return dashboard
