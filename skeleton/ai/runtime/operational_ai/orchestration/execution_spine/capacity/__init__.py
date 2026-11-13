"""Bounded, evidence-aware preflight for the operational AI inference spine.

Preflight is read-only and must finish before a pending inference lease exists.
The original conversation and knowledge sources remain in their authority
stores; a candidate context is explicitly a *loss-accounted projection*.
"""
from .planner import prepare_context
from .contracts import CapacityPlan, CapacityPolicy
from .proofs import validate_decision, describe_decision

__all__ = ["prepare_context", "CapacityPlan", "CapacityPolicy",
           "validate_decision", "describe_decision"]
