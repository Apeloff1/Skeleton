"""Independent real-model conformance lane for Skeleton native offline inference.

Model quality can be *measured*, never inferred from static fixtures.
No fixture backend or hosted fallback is available through this package.
"""
from .cases import QualificationCase, Step
from .runner import NativeQualificationRunner
from .report import QualificationReport

__all__ = ["QualificationCase", "Step", "NativeQualificationRunner", "QualificationReport"]
