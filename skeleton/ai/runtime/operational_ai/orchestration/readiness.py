"""Explicit evidence for AI runtime composition; no percentage theater."""
from __future__ import annotations
from ..authority.canonical import ContractViolation
from .service import OfflineAIService


def readiness(service:OfflineAIService)->dict:
    checks={
        "native_backend_bound":bool(service.gateway.backend.model_digest and service.gateway.backend.tokenizer_digest),
        "conversation_authority_connected":hasattr(service.store,"load") and hasattr(service.store,"commit"),
        "memory_authority_connected":hasattr(service.memory,"admit") and hasattr(service.memory,"search"),
        "tool_policy_independent":hasattr(service.tools,"invoke"),
        "journal_integrity":service.journal.head("operational_ai_health")[0]>=0,
        "nonzero_budgets":service.limits.output_tokens>0,
    }
    return {"state":"assembled-local-unqualified" if all(checks.values()) else "blocked",
            "checks":checks,"warning":"Assembly checks do not prove model quality or deployment readiness"}
