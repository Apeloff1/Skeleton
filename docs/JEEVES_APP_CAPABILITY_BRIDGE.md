# Jeeves app capability bridge

Jeeves can now inspect the canonical machine AI file-tree, architecture roots,
and capability-interface registry through a bounded, deterministic, hash-based
projection instead of loading all repository files into model context.

The bridge exposes:
- `Jeeves.app_capability_catalog(query, limit, offset)` — 64-row maximum,
  canonical mapping identifiers, source/destination, owner-root and mirror mode.
- `Jeeves.creator_proposal(operation, project_id, payload)` — canonical B014
  `CreatorCommand` validation and SHA-256 content identity.
- `Jeeves.app_tool_registry()` — three read-only tools using the existing
  `ToolRegistry`: `app.capabilities`, `creator.operations`, and
  `creator.propose`.

The host must still supply a `ToolGrant` and execute via `ToolExecutor` or
the stronger `PermitBoundToolExecutor`; merely seeing an indexed feature is
**not** proof that its runtime exists or that Jeeves can edit it. No generic
file writer, shell, editor, export or deployment tool is registered here. New
mutating handlers must be implemented through the existing creator command,
work-lease, approval, and runtime-evidence planes, not by granting model-owned
filesystem authority.

The machine-index digest is stable across calls when the canonical mapping
remains unchanged. No source files are opened during paged search, and the
LLM cannot choose an arbitrary manifest path. Each response states explicitly
that it grants no execution authority.

This is a substantive app-discovery/control-plane integration, **not a claim**
that every editor or every game engine is already accessible to Jeeves.

## Opt-in editor action execution

Trusted hosts may separately call `register_authorized_creator_tool(registry,
handlers=..., authorize=...)`. This does **not** occur in
`Jeeves.app_tool_registry()`; it adds `creator.execute_authorized` only
when the host provides real creator operation handlers and a callable
authorization verifier. The verifier receives the normalized B014 command and
actual `ToolExecutionContext`, and must return literal `True` for the exact
command/run/user/lease/approval evidence before the handler is called.

The `ToolExecutor` independently requires a `HIGH_IMPACT` `ToolGrant`
with a bounded per-run call budget. A rejected authorization consumes the
presented grant attempt. No `authorize` or `handler` value can be supplied
in model arguments. The tool is neither cached nor idempotently replayed.
This is a host integration adapter, not an LLM-controlled write credential.

## Concept-level search (declared versus implemented)

`Jeeves.app_capability_concepts(query, limit, offset)` and the read-only
`app.concepts` host tool now page through the canonical
`machine/capability_taxonomy.json` concept list (1,215 declarations at
introduction). This supplements the 179 source/destination file-tree
mappings, without loading a thousand concepts or the entire repository into
one model response.

Each result has a stable concept ID, a small set of declared aliases,
volume references, and `implementation_verified=false`. Declared concepts
do **not** imply working code. Actual execution continues to require an
installed host handler, a high-impact grant, and authorization of the exact
creator command identity.
