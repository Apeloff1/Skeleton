# Operational AI capacity admission

This module prepares one *ephemeral* model context from verified conversation
history and operator-admitted source excerpts. It performs no inference, tool
call or database write. The authoritative transcript is kept intact; omitted
turns and sources are always explicitly accounted for and cryptographically
bound into the durable turn receipt once inference succeeds.

The planner preserves complete user/assistant turn pairs; it drops oldest
history first, then lowest-ranked evidence. The current user prompt is never
trimmed. A prompt that cannot fit by itself must fail **before** a request is
reserved. Relevance order is supplied by the evidence provider and is not a
proof of factual correctness.

A native `count_tokens()` method is used only when available. The GGUF backend
currently does not expose a chat-template-aware exact count, so its pre-count
remains labeled **unverified** even when a conservative byte estimate allows
inference. The native generation receipt still enforces its context ceiling.
Do not label a portable preflight as an exact-token or quality certificate.

`CapacityPolicy(require_native_precount=True)` is an explicit fail-closed
qualification profile. All content in evidence remains untrusted data.
