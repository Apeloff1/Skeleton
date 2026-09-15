# Provider-neutral model runtime

Issue #116 defines the canonical boundary between orchestration code and model/provider SDKs.

## Contract

Core code should depend on `skeleton.frontier.model_runtime` request and response types, not OpenAI, LiteLLM, Google GenAI, or other vendor response objects.

The contract covers:

- chat messages and responses;
- tool definitions and normalized tool calls;
- streaming text/tool-call deltas;
- embedding requests and vectors;
- structured JSON output;
- token accounting metadata;
- provider capability negotiation;
- deterministic timeout and cancellation behavior; and
- bounded retry of explicitly transient failures.

`ModelRuntime` is the registry and policy boundary. Adapters declare a `frozenset[ModelCapability]`; unsupported capabilities fail closed unless the caller explicitly opts into a documented fallback.

## Adapters

Two maintained dependency shapes are covered by the shared contract tests:

- `OpenAIChatCompletionsAdapter` accepts an injected OpenAI 2.x `AsyncOpenAI`-style client and translates Chat Completions plus embeddings into frontier types.
- `LiteLLMAdapter` accepts an injected LiteLLM module/object exposing `acompletion` and `aembedding` and translates its OpenAI-compatible shapes into the same frontier types.

Adapters intentionally use duck typing and do not import provider SDK packages from the frontier layer. This keeps `skeleton` importable without optional provider packages and prevents provider-specific types from leaking into orchestration code.

## Current provider audit

The production dependency graph previously carried `google-genai`, but the #116 audit found no active Python model-execution import or client call site for that SDK. The unused production dependency is therefore removed rather than creating an adapter for code that does not exist.

`scripts/check_provider_runtime_boundary.py` makes that conclusion enforceable: direct or dynamic Google GenAI imports under runtime source roots fail CI. Adding Google later requires an intentional canonical `ProviderAdapter` plus the same shared contract tests used by the maintained adapters before the boundary gate is relaxed.

`backend/server.py` still contains one legacy import of the repository-local, boot-safe `emergentintegrations.llm.chat` compatibility shim. The audit verifies that `LlmChat` and `UserMessage` are not used by the server and rejects retired Emergent imports anywhere else in runtime source. Any future attempt to turn that compatibility import into a live provider call therefore fails the canonical quality gate.

The same boundary scanner rejects direct OpenAI, LiteLLM, Google, or Emergent SDK imports from `skeleton/frontier` and `skeleton/agents`, keeping provider-specific types out of core orchestration and agent execution code.

## Capability fallbacks

Fallbacks are explicit rather than automatic:

- structured output can fall back to ordinary chat plus strict JSON-object decoding only when `allow_structured_fallback=True`;
- streaming can fall back to a single non-stream chat result only when `allow_nonstream_fallback=True`;
- tool calling and embeddings have no implicit fallback.

## Cancellation, timeout, and retry

A `CancellationToken` can abort an in-flight model operation without exposing provider cancellation primitives. `timeout_seconds` is an overall deadline for an operation including retries. Only `TransientProviderError` is retried, bounded by `RetryPolicy.max_attempts`; timeouts, cancellation, capability errors, and ordinary provider errors are not silently retried.

Streaming is not replayed after partial delivery because retrying a partially emitted stream would duplicate externally visible output.

## Migration rule

New orchestration code should accept or resolve a `ProviderAdapter` through `ModelRuntime`. Existing direct SDK calls should migrate behind adapters incrementally. Provider-only request knobs belong inside adapters or future adapter configuration objects; adding vendor fields to `ChatRequest`/`ChatResponse` is not an accepted migration path.
