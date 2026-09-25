# AI Assistant Control Plane — Clean-Room Capability Port

Date: **2026-09-25**

Status: **implemented candidate; exact-head CI and independent verification required**

Canonical code: `skeleton/ai/assistant/`

Machine contract: `machine/ai_assistant_control_plane.json`

Validator: `scripts/check_ai_assistant_control_plane.py`

## Purpose

This packet brings high-value product-assistant patterns visible in a modern
tool-using AI experience into Skeleton's canonical AI tree without copying any
vendor-private implementation. It does **not** contain or claim access to model
weights, private provider source, hidden prompts, credentials, or hidden
reasoning traces.

The new layer sits above Skeleton's existing context, cognitive-execution,
provider, memory, tool, artifact and streaming planes. Its job is to decide
*which governed capability is needed*, assemble safe context, enforce
least-authority execution, and preserve a replayable handoff/provenance record.

## Implemented surfaces

### Deterministic capability routing

`routing.py` separates synthesis from evidence/action dependencies. Fresh
public facts route to public retrieval; references to prior personal context
route to personal-context retrieval; attachments route to files; requested
side effects route to external apps; future/recurring work routes to automation;
artifact and image requests route to their dedicated surfaces.

Routing reasons are structured reason codes, not hidden reasoning text.

### Trust-aware context compiler

`context.py` orders trusted control before user/private/public/tool/model
content, removes expired or unauthorized restricted material, deduplicates
content deterministically, and fails closed rather than silently dropping
trusted control when the context budget is too small.

Instruction-shaped text from retrieval or tools remains evidence and cannot
promote itself into policy.

### Capability registry and authority

`capabilities.py` gives each surface a declared kind, side-effect class,
scopes, and I/O bounds. Scoped reads and all writes require request-bound
grants. External/security-sensitive writes additionally require explicit user
action. Requested scopes cannot exceed the descriptor's declared authority.

### Bounded idempotent tool loop

`tooling.py` binds proposals to the request digest, verifies side-effect
classification, enforces per-capability input/output bounds and request call
budgets, and preserves idempotency across retries. Reusing an idempotency key
for different arguments fails closed. Authorization denials do not consume the
key, allowing a later correctly-authorized retry.

### Memory policy

`memory.py` keeps retrieval and durable persistence separate. Prior-context
references can trigger retrieval, while durable writes require longer-lived
utility and reject sensitive persistence unless the user explicitly requests
it. Forgetting is also an explicit-user operation.

### Automation and artifacts

`automation.py` models exact, flexible, and condition-watch timing and rejects
recurrence faster than the one-hour control-plane floor.

`artifacts.py` resolves explicit artifact intent to document, spreadsheet,
presentation, PDF, image, code, or generic artifact capability surfaces without
mistaking a request to *read* an existing PDF/document for a request to create
one.

### Immutable execution handoff and provenance

`handoff.py` produces a provider-neutral immutable boundary containing the
request, route, context digest, allowed capabilities, evidence refs, and tool
budget. `provenance.py` binds final response identity to route/context/tool
receipts and evidence without storing private reasoning traces.

`runtime.py` composes the entire control plane and reports required capability
kinds that are not currently available.

## Existing Skeleton integration

The packet deliberately composes rather than replaces:

- `skeleton/ai/runtime/intelligence/execution_runtime.py` for bounded durable
  model/tool execution;
- `skeleton/ai/runtime/contracts/context.py` for canonical context semantics;
- `skeleton/ai/providers/runtime.py` for provider isolation;
- `skeleton/ai/runtime/skills/tool_adapters/` for tool-facing adapter policy;
- the existing Stage-6 durable operation streaming/reconciliation plane for
  product delivery.

The assistant handoff can feed the cognitive runtime without granting the model
new authority.

## Regression evidence included

The focused tests cover:

- fresh/current information routing;
- personal/file dependency routing;
- existing-PDF read vs PDF creation intent;
- ordinary future-date questions vs automation intent;
- prompt-injection-shaped public evidence;
- restricted/expired context rejection;
- trusted-control budget exhaustion;
- content dedupe preferring higher trust;
- external write confirmation + request-bound scopes;
- scoped read permission enforcement;
- per-capability input bounds;
- tool idempotent replay and conflicting-key rejection;
- sensitive memory persistence;
- sub-hour condition-watch rejection;
- runtime handoff and provenance binding.

No completion checkbox or independent verification signature is fabricated by
this packet.
