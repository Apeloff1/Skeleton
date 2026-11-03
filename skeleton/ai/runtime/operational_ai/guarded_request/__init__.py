"""Fail-closed, offline-only ingress and capacity contracts.

The authoritative NativeChatEngine and OfflineAIService remain the only
inference and chat owners. This package never substitutes generated replies.
"""
from .errors import GateDenied
from .workflow import GuardedDispatcher
from .budgets import Quota, QuotaUsage
from .identities import Scope

__all__ = ["GateDenied", "GuardedDispatcher", "Quota", "QuotaUsage", "Scope"]
