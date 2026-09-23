"""Compatibility facade for the engine-owned AI provider runtime.

Canonical provider execution now lives in :mod:`skeleton.provider_runtime`.
Backend imports are retained so existing routes/services can migrate without a
flag day. This module must not acquire credentials, SDK imports, provider
network policy, or provider business logic.
"""

from __future__ import annotations

from skeleton import provider_runtime as _runtime

AIMessage = _runtime.AIMessage
OpenAIProviderAdapter = _runtime.OpenAIProviderAdapter
ProviderAdapter = _runtime.ProviderAdapter
ProviderError = _runtime.ProviderError
ProviderImageRequest = _runtime.ProviderImageRequest
ProviderImageResponse = _runtime.ProviderImageResponse
ProviderInvocationError = _runtime.ProviderInvocationError
ProviderPolicyError = _runtime.ProviderPolicyError
ProviderRegistry = _runtime.ProviderRegistry
ProviderRequest = _runtime.ProviderRequest
ProviderResponse = _runtime.ProviderResponse
ProviderSpeechRequest = _runtime.ProviderSpeechRequest
ProviderSpeechResponse = _runtime.ProviderSpeechResponse
ProviderUnavailableError = _runtime.ProviderUnavailableError
normalize_history = _runtime.normalize_history
provider_request_from_context = _runtime.provider_request_from_context

# Historical compatibility exports used by focused tests and older callers.
ProviderArchitectureError = _runtime.ProviderArchitectureError
ProviderArchitectureReceipt = _runtime.ProviderArchitectureReceipt
load_provider_architecture = _runtime.load_provider_architecture
_validate_provider_base_url = _runtime._validate_provider_base_url
_validate_request = _runtime._validate_request
_estimated_input_tokens = _runtime._estimated_input_tokens
_provider_operation_id = _runtime._provider_operation_id


def __getattr__(name: str):
    """Forward transitional attribute access to the canonical runtime module."""

    return getattr(_runtime, name)


__all__ = list(_runtime.__all__)
