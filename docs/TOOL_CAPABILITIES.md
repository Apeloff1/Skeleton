# Tool capability contract

The canonical orchestrator treats sensitive tool capabilities as explicit run-time grants rather than ambient process authority.

## Capabilities

Registered tools may declare one or more of these capabilities:

- `filesystem`
- `network`
- `process`
- `secrets`
- `repository_mutation`

A tool with no declared capability remains compatible with the existing `ToolRegistry.register(name, handler)` API. A tool that declares a sensitive capability is denied unless the caller grants that capability explicitly to `CanonicalOrchestrator.run(..., capabilities=...)`.

## Deny by default

Runs start with no sensitive capabilities. The orchestrator checks every declared capability before invoking a handler. A missing grant fails the tool step and the run without calling the handler.

Capability names are closed over the `ToolCapability` enum. Unknown capability strings are rejected during registration or run setup instead of being treated as implicit authority.

## Audit records

Each declared capability produces a `CapabilityDecision` on the `RunRecord`. The record contains:

- run ID
- tool call ID
- tool name
- capability
- allow/deny decision

This keeps authorization decisions attached to the orchestration run that made them and makes denials deterministic and testable.

## Migration rule

New tools that touch the filesystem, network, subprocesses, secrets, or repository mutation must declare the matching capability when they are registered. Existing capability-free tools do not need to change until they cross one of those sensitive boundaries.

Do not bypass this contract by performing sensitive work in an undeclared handler or by adding a parallel tool-execution path outside the canonical orchestrator.
