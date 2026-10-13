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
