"""#807 batch B039: self-repair and bounded optimization (lane ai, wave 3)."""
from .self_repair import (
    Budget, BudgetExceeded, Diagnosis, EvalFailure, EvalResult, Mutation,
    ProvenanceRecord, RepairLoop, RepairOutcome, RouteChoice, diagnose,
)

__all__ = [
    "Budget", "BudgetExceeded", "Diagnosis", "EvalFailure", "EvalResult", "Mutation",
    "ProvenanceRecord", "RepairLoop", "RepairOutcome", "RouteChoice", "diagnose",
]
