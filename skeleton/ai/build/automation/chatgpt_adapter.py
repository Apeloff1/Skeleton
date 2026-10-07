"""Compatibility facade for the canonical repository ChatGPT adapter.

The AI build tree may import the repository-automation reasoner, but credential
reads, provider-network transport, cancellation behavior, and architecture
receipts remain owned by :mod:`skeleton.automation.chatgpt_adapter`.
"""

from skeleton.automation.chatgpt_adapter import (
    ChatGPTReasoner,
    ReasoningRequest,
    ReasoningResult,
    require_repository_provider_credentials_absent,
)

__all__ = [
    "ChatGPTReasoner",
    "ReasoningRequest",
    "ReasoningResult",
    "require_repository_provider_credentials_absent",
]
