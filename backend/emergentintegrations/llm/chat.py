"""Local source-compatible facade for the retired Emergent chat SDK.

The third-party ``emergentintegrations`` dependency is no longer installed.
Historical backend modules still import this local module by its old package
name, so keep that import path stable while delegating all supported text
execution to ``core.ai_provider_compat`` and, through it, the canonical provider
runtime.

New code must import ``core.ai_provider`` directly. This module exists only to
make the legacy source surface safe and centrally auditable during migration.
"""

from core.ai_provider_compat import ChatResponse, LlmChat, UserMessage

__all__ = ["ChatResponse", "LlmChat", "UserMessage"]
