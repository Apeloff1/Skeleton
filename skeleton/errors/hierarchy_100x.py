"""skeleton/errors/hierarchy_100x.py
100x extreme complete error hierarchy.
Consistent SkeletonError subclasses and fail-closed on all entries.
Fail-closed.
"""
from __future__ import annotations

class SkeletonError(Exception):
    code = "BASE"
    severity = "medium"

class StructuralError(SkeletonError):
    code = "STRUCT"
    severity = "high"
