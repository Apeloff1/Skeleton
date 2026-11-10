"""Builder edit loop: instruction -> typed diff -> apply -> revalidate -> undo/redo.

History persistence is injected through :class:`ProjectHistoryLike`, which
mirrors the project bundle history API (feat/mb-project-bundle-oyvind-20261031);
that package is never imported here.
"""
from __future__ import annotations

from .diff import DiffError, EditOp, PlanDiff, apply_diff, invert
from .model_edit import EditPlanner, EditProposal
from .protocol import ProjectHistoryLike, ProjectSaverLike
from .rules import rule_based_diff
from .session import EditRecord, EditResult, EditSession

__all__ = [
    "DiffError", "EditOp", "EditPlanner", "EditProposal", "EditRecord", "EditResult", "EditSession",
    "PlanDiff", "ProjectHistoryLike", "ProjectSaverLike", "apply_diff", "invert", "rule_based_diff",
]
