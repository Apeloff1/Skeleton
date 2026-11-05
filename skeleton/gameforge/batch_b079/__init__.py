"""#807 batch B079: cross-platform compatibility matrix (lane quality, wave 3; depends on B074, B075)."""
from .matrix import CompatMatrix, MatrixError, Platform, ScenarioOutcome

__all__ = ["CompatMatrix", "MatrixError", "Platform", "ScenarioOutcome"]
