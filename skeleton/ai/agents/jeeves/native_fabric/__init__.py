"""Deterministic offline native-AI control fabric for Jeeves.

This package contains pure host-side operations. It never loads a model,
contacts a hosted provider, grants filesystem access, or authorizes a tool.
Proposed model actions must separately pass the existing strict runtime,
native installer proof, and canonical SQLite execution spine.
"""
from .contracts import ContractHold, Scope, ResourceLimits, Proof, Verdict
from .budgets import ResourceBudget, BudgetLedger, BudgetTicket
from .events import EventJournal, Event, validate_journal
from .plans import TaskGraph, TaskNode, TaskState, PlanHold

__all__ = [
    "ContractHold", "Scope", "ResourceLimits", "Proof", "Verdict",
    "ResourceBudget", "BudgetLedger", "BudgetTicket",
    "EventJournal", "Event", "validate_journal",
    "TaskGraph", "TaskNode", "TaskState", "PlanHold",
]
