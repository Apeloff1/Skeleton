"""Observability subsystem — metrics, tracing, health, emergent-coupling detection."""

from .entanglement import Entanglement, EntanglementDetector

__all__ = [
    "Entanglement",
    "EntanglementDetector",
]
