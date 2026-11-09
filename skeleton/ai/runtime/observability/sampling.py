"""
Skeleton Observability — Sampling module

Provides:
- Sampler: Adaptive telemetry sampling (re-export hub)
- default_sampler: Factory
"""

from __future__ import annotations

from skeleton.observability.metrics import Sampler, default_sampler

__all__ = ["Sampler", "default_sampler"]
