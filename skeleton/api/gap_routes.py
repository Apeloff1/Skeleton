"""skeleton/api/gap_routes.py
Complete route example exposing multi-gap health and metrics.
Fail-closed. No stubs.
"""
from __future__ import annotations

from typing import Any

from skeleton.app.gap_health import health_card
from skeleton.app.gap_metrics import metrics_summary

def get_health() -> dict[str, Any]:
    """Return the readiness health card."""
    return health_card()

def get_metrics() -> dict[str, Any]:
    """Return the metrics summary."""
    return metrics_summary()

def get_status() -> dict[str, Any]:
    """Return the full status card."""
    from skeleton.app.gap_status import generate_status
    return generate_status()
