"""GF-M qualification harness (Game Frontier P3, issue #4170).

Evaluates declared qualification cases against recorded evidence and emits
verdicts. The harness never fabricates evidence: a case whose evidence is
absent is reported BLOCKED, and cases that need real hardware stay unclaimed
until evidence bound to an exact head SHA is supplied.
"""
from .errors import QualificationError, SchemaError
from .schema import QualCase, load_case, parse_case
from .evidence import Evidence, load_evidence
from .verdict import Verdict, CaseResult, aggregate
from .runner import run_cases

__all__ = [
    "QualificationError", "SchemaError", "QualCase", "load_case", "parse_case",
    "Evidence", "load_evidence", "Verdict", "CaseResult", "aggregate", "run_cases",
]
