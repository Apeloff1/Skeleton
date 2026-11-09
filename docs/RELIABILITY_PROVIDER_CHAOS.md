# Backend provider failure chaos

This profile complements the canonical stream reliability work under issue #123 by exercising the backend OpenAI adapter and HTTP-facing AI route boundary without calling an external model API.

## Fault model

`backend/tests/test_ai_provider_reliability.py` uses deterministic in-process fault injectors around `OpenAIProviderAdapter` and `routes.ai.call_llm()`.

The profile protects three backend-specific invariants:

1. **Concurrent timeout burst:** 32 concurrent provider calls raise injected `TimeoutError` failures. Every call must terminate as the same sanitized `ProviderInvocationError`; raw upstream detail must not appear in the public exception text.
2. **Explicit SDK resilience bounds:** client construction must receive the configured `timeout`, `max_retries`, API key, and optional base URL exactly. This guards accidental loss of bounded provider retry/timeout configuration during adapter refactors.
3. **Route-level failure sanitization:** an adapter that raises a provider failure containing secret-like upstream detail must produce only the generic `provider_unavailable` result, while logs identify the exception class without the upstream detail.

The timeout burst deliberately uses an injected client, so it tests the repository-owned adapter boundary rather than duplicating the OpenAI SDK's internal retry implementation. The construction invariant separately verifies that production SDK retry behavior remains bounded by `AI_MAX_RETRIES` and the configured timeout.

This is separate from `docs/PROVIDER_STREAM_RELIABILITY.md`, which covers `ModelRuntime.stream_chat()` retry integrity, concurrent streaming pressure, and pre/post-emission provider failures.

## Run locally

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest -q --noconftest \
  tests/test_ai_provider_reliability.py
```

The regression is wired into both `scripts/quality-gates.sh` and the Backend Quality workflow.

## Remaining reliability work

With stream/provider failure coverage and durable-storage chaos now represented, issue #123 remains open for broader process-level memory/resource soak evidence and an actual representative-environment capacity result captured with the documented baseline protocols.
