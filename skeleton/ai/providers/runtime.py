"""Compatibility facade for the canonical provider runtime.

The credential-bearing implementation intentionally remains owned by
`skeleton.provider_runtime` until the import/ownership cutover declared in
`machine/ai_file_tree.json` is complete. This module must never acquire
provider credentials, SDK imports, or network behavior of its own.
"""

from skeleton.provider_runtime import (
    AIMessage,
    OpenAIProviderAdapter,
    OpenAISyncProviderAdapter,
    ProviderAdapter,
    ProviderError,
    ProviderImageRequest,
    ProviderImageResponse,
    ProviderInvocationError,
    ProviderPolicyError,
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
    ProviderSpeechRequest,
    ProviderSpeechResponse,
    ProviderUnavailableError,
    normalize_history,
    provider_request_from_context,
)

__all__ = [
    "AIMessage",
    "OpenAIProviderAdapter",
    "OpenAISyncProviderAdapter",
    "ProviderAdapter",
    "ProviderError",
    "ProviderImageRequest",
    "ProviderImageResponse",
    "ProviderInvocationError",
    "ProviderPolicyError",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResponse",
    "ProviderSpeechRequest",
    "ProviderSpeechResponse",
    "ProviderUnavailableError",
    "normalize_history",
    "provider_request_from_context",
]
