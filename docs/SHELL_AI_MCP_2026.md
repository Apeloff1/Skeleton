# Shell AI MCP 2026 Integration

## Scope

This document describes the transport-neutral MCP-compatible shell tool surface.

The implementation targets the 2026-07-28 protocol generation.

It does not implement an HTTP server.

It provides the data model and gateway semantics needed by a transport adapter.

## Why MCP exists here

Skeleton already has an internal AI model protocol.

MCP serves a different purpose.

The internal protocol lets a planner return a multi-action proposal.

The MCP surface lets an external agent runtime discover and call reviewed
logical tools.

Both paths converge on AIAction and deterministic policy.

Neither path owns subprocess execution.

## Stateless design

MCPRequestEnvelope is self-contained.

It carries:

protocol revision

request ID

method

tool name

arguments

bounded metadata

No server session is required to interpret one request.

Application-level AIShellSession remains available for workflows that need
review and execution state.

Protocol statelessness and application sessions are separate concepts.

## Protocol revision

MCP_PROTOCOL_REVISION is 2026-07-28.

MCPAIShellGateway rejects requests with another revision.

A future revision should be added deliberately.

Do not silently interpret breaking revisions.

## Tool discovery

MCPToolSurface builds tool descriptors from AIToolManifest.

The source therefore remains:

CommandCatalog

AIToolCatalog

EffectRegistry

response schema

No independent MCP-only command registry exists.

This avoids contract drift.

## Tool descriptor

MCPToolDescriptor contains:

name

description

inputSchema

outputSchema

annotations

Input and output schema roots are objects.

## Input schema

Current input fields:

args

cwd

environmentRefs

timeoutSeconds

purpose

The schema disallows unspecified top-level fields.

MCPAIShellGateway validates important types again when preparing a call.

## Output schema

The model-facing output schema is observation-oriented.

It includes:

ok

observationId

returncode

timedOut

outputLimited

stdoutBytes

stderrBytes

stdoutDigest

stderrDigest

Raw child output is not part of the default output schema.

## Tool annotations

Current annotations include:

effects

idempotent

reversible

approvalRecommended

Annotations help agents and UIs.

They do not grant authority.

## Executable paths

Executable host paths are never exported.

The MCP client sees logical command names.

ShellPolicy remains responsible for executable resolution.

## Tool list

MCPToolList contains:

protocolRevision

tools

ttlMs

cacheScope

digest

Tool ordering is deterministic.

Digest changes when exported descriptors change.

## Cache behavior

ttlMs is an optimization hint.

cacheScope can be:

public

private

no-store

A cached tool list does not authorize a stale call.

The gateway validates current tools.

AIShellService later validates stale plan pins.

## Routing headers

MCPRequestEnvelope exposes routing headers:

Mcp-Method

Mcp-Name

A transport gateway can use these for:

routing

rate limiting

metrics

authorization lookup

A real transport must verify that routing headers agree with parsed body state.

## Authorization

MCPAuthorization maps authenticated principal to MCPPrincipalPolicy.

Policy can define:

allowed tools

denied tools

maximum timeout

Unknown principals are denied.

Denied tools win over open allowlists.

## Principal identity

Principal must come from authenticated transport or application context.

Do not take principal from model output.

Do not take principal from unverified request metadata.

## Layered authorization

MCP authorization is the first remote-call layer.

It is not sufficient by itself.

A prepared action still passes:

AI intent constraints

AI tool guardrails

effect risk

AIShellPolicy

human approval where required

stale-plan checks

ShellService

ShellExecutor

ShellRunner

## Gateway

MCPAIShellGateway performs:

protocol revision check

method check

tool existence check

argument shape check

environmentRefs shape check

timeout conversion

principal authorization

AIAction construction

It does not call ShellService.

It does not call ShellRunner.

## Supported method

The action gateway currently accepts tools/call.

Tool listing is exposed through list_tools.

Other MCP features should be integrated separately.

Do not overload tools/call with resource or prompt behavior.

## Prepared tool call

MCPPreparedToolCall contains:

original request

authenticated principal

AIAction

This is a preparation artifact.

It is not an execution receipt.

## Converting to AI intent

An application can wrap a prepared tool call into an AIIntent with strict
allowed_commands containing only the selected tool.

Recommended constraints:

max_steps = 1

allow network based on effect contract

allow writes based on reviewed caller policy

destructive permission based on explicit caller policy

short timeout ceiling

Then run the normal AI shell review path.

## Approval

MCP clients should not imply approval merely by calling a tool.

If AIShellPolicy requires approval:

return a pending-review state

create AIReviewQueue item

obtain authenticated human decision

create AIPlanApproval

execute after approval

Do not reinterpret an MCP request as human consent.

## Long-running tasks

MCPTaskRegistry models task lifecycle.

States:

pending

running

succeeded

failed

cancelled

Creating a task starts no background work.

## Task binding

A task should reference:

request ID

principal

tool

correlation ID

The application should separately bind the task to execution evidence.

Task ID is not authority.

## Task transitions

PENDING may become:

RUNNING

CANCELLED

FAILED

RUNNING may become:

RUNNING

SUCCEEDED

FAILED

CANCELLED

Terminal tasks reject mutation.

## Progress

Progress ranges from zero to one.

SUCCEEDED forces progress to one.

Progress is informational.

It does not change execution priority or authority.

## Cancellation

Task cancellation changes task state only.

If live child cancellation is needed, connect it to AIShellSession cancellation
and the lower shell cancellation boundary.

Do not kill arbitrary PIDs from MCPTaskRegistry.

## Errors

MCPResponseEnvelope separates:

ok

result

error code

error message

A successful response cannot also carry an error field.

Keep error messages bounded.

Do not echo child output into transport errors.

## Remote transport requirements

A real network transport should add:

TLS

authenticated principal derivation

issuer validation

audience validation

request byte limits

connection rate limits

tool rate limits

origin policy where relevant

body/header consistency checks

structured logging with redaction

timeout ceilings

replay protection where applicable

## Authorization server integration

Keep OAuth or enterprise authorization outside the core AI shell modules.

Translate authenticated identity into MCPPrincipalPolicy lookup.

Do not let OAuth scopes directly become ShellCapability without explicit mapping.

## Tool-list visibility

The current MCPToolSurface can generate the full configured list.

A remote service may filter discovery by principal.

Filtering should use authorization policy.

The filtered list should get its own digest.

## Multi-instance deployment

The protocol surface is stateless.

The application control plane may still require shared durable state for:

policy revisions

review queue

approval registry

quarantine

idempotency

task registry

decision journal

receipt evidence

Use transactional shared storage in a distributed deployment.

## Load balancing

Because request envelopes are self-describing, transport instances can be
stateless.

Do not rely on sticky routing for authorization state unless explicitly
designed.

## Catalog change

When tools change:

generate new list digest

expire old list according to cache policy

invalidate reviewed plan pins through tool digest change

rerun MCP contract tests

rerun AI evals if model-visible semantics changed

## Effect change

An effect change changes AIToolManifest digest.

Review the change.

A reviewed plan using old effect digest becomes stale.

## Schema change

Input-schema change can break clients.

Treat it as a versioned contract change.

Output-schema change can break agents and UIs.

Run compatibility tests before release.

## MCP compatibility testing

Test:

revision

tool ordering

digest stability

ttlMs

cacheScope

object input schema

object output schema

annotations

path redaction

routing headers

authorization

unknown principal

unknown tool

timeout ceiling

wrong method

wrong revision

task transitions

terminal task immutability

## Security rule

MCP is a transport and tool-discovery layer.

It must not become an alternate execution authority.

Every path must converge back into the same AI shell and ShellService controls.
