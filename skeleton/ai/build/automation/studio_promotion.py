"""Promotion gate from validated work to publishable candidate."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class PromotionEvidence:
    validation_passed:bool; review_passed:bool; receipt_bound:bool; worktree_clean:bool
def promotable(e:PromotionEvidence)->bool:
    return e.validation_passed and e.review_passed and e.receipt_bound and e.worktree_clean
def require_promotable(e:PromotionEvidence)->None:
    if not promotable(e): raise ValueError("candidate is not promotable")
