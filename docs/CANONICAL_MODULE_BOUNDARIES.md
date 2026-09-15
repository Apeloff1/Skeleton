# Canonical module boundaries

This document is the consolidation ownership contract for Skeleton. It complements `docs/ARCHITECTURE.md`: the architecture treatise explains how the system works, while this file answers a narrower question required during consolidation — **which package owns each capability, which dependency directions are allowed, and what happens to overlapping implementations**.

The rule is intentionally conservative: a capability gets one canonical owner. Compatibility shims may exist during migration, but they must delegate into that owner and must not grow a second implementation.

## Dependency direction

The default direction is:

```text
UI / CLI / API adapters
        |
        v
application orchestration / agents / Jeeves / forge / pipelines
        |
        v
runtime, state, memory, tools and domain services
        |
        v
kernel contracts and identifiers
```

Dependencies may point downward or sideways through an explicit contract. They must not point upward into an interface adapter.

Two rules are enforced immediately by `scripts/check_architecture_boundaries.py`:

1. `skeleton/kernel/**` cannot import web frameworks, network/database clients, or `skeleton.api`.
2. production modules under `skeleton/**` cannot import `skeleton.api` unless they are themselves API adapters or the top-level CLI entry point.

These checks deliberately start with the highest-risk reverse dependencies. Additional edges should be added only after the current tree is migrated cleanly; architecture enforcement must not be weakened by broad allowlists.

## Canonical ownership matrix

| Capability | Canonical owner | Allowed responsibilities | Must not own |
| --- | --- | --- | --- |
| Kernel primitives | `skeleton/kernel/` | typed errors, IDs, event/capability contracts, dependency-free primitives | HTTP, persistence, provider SDKs, process/network I/O |
| Agent orchestration | `skeleton/agents/` | agent roster, scheduling, consensus, orchestration-facing agent contracts | provider-specific transport, API routing, UI state |
| Model/runtime execution | canonical runtime contract promoted under `skeleton/frontier/` until a dedicated `skeleton/runtime/` package is introduced | provider-neutral request/response, streaming, cancellation, capability negotiation, accounting | agent policy, HTTP endpoint semantics, vendor fields in core contracts |
| Memory / RAG | `skeleton/jeeves/rag.py` for the current canonical retrieval contract; future generalized retrieval must migrate behind one shared `skeleton/memory/` contract before callers move | document/chunk retrieval, ranking, provenance, storage adapters behind one interface | tutor policy, API serialization, duplicated vector-store facades |
| Tool execution | capability contracts in the kernel/frontier layer with execution adapters outside the kernel | declared capabilities, invocation lifecycle, audit metadata, sandbox boundary adapters | ambient unrestricted process/filesystem/network access |
| Jeeves / learning | `skeleton/jeeves/` | tutoring session policy, learning matrices, co-coding behavior, Jeeves-owned retrieval integration | generic provider transport, public HTTP concerns |
| Game/world domain | canonical game/world implementations promoted under `skeleton/` domain packages and referenced from the consolidation manifest | world/game state and deterministic domain behavior | HTTP/UI coupling, duplicate experimental copies treated as production |
| Forge | `skeleton/forge/` | blueprint validation, composition, materialization and forge-domain quality gates | API routing, UI state, generic runtime/provider ownership |
| Pipelines | `skeleton/pipelines/` | staged artifact generation and domain pipeline composition | provider-specific transport, persistent state implementation |
| State / checkpoints | `skeleton/state/` when present as the durable-state surface | versioned run/checkpoint records, migration, idempotent recovery contracts | business policy, API response formatting |
| Public API | `skeleton/api/` for the root Skeleton service; `backend/` remains a separately bounded legacy/application surface until explicitly migrated | transport validation, auth/middleware, HTTP/WebSocket serialization, application wiring | domain algorithms, duplicate orchestration loops |
| CLI | `skeleton/__main__.py` plus thin command adapters | argument parsing, command UX, invocation of shared services | business logic that diverges from API/service behavior |
| UI | `frontend/` and explicit client packages | presentation, client state, API consumption | server trust decisions, secret handling, canonical domain state |

### Transitional owners

Some consolidation workstreams do not yet have a single dedicated package. The matrix still chooses a direction instead of pretending duplication is acceptable:

- Provider-neutral runtime work remains a **contract-first frontier workstream** until its stable package is promoted. Existing provider adapters must target that shared contract rather than creating new agent-local execution APIs.
- Jeeves RAG is the current implemented retrieval owner. A generalized memory package may replace it only through an explicit migration with shared contract tests and provenance preservation; do not add another independent retrieval facade meanwhile.
- Game/world code may have several experimental or mined implementations. Promotion requires one canonical destination and provenance entry before callers adopt it.
- `backend/` is not a second owner for root Skeleton domain primitives. It may keep its application-specific middleware/routes while consolidation proceeds, but shared domain/runtime capabilities should move behind reusable contracts rather than being copied in both trees.

## Duplicate and legacy implementation policy

A duplicate implementation must be classified as exactly one of:

1. **Canonical** — the implementation new callers use.
2. **Compatibility shim** — delegates to canonical behavior and has a removal issue/date.
3. **Experimental** — isolated from production imports and clearly named/documented as non-canonical.
4. **Migration source** — frozen except for security/correctness fixes while behavior is transplanted.
5. **Archive/reject** — retained only for provenance/history or removed from the active tree after migration.

The `skeleton/architecture_round*.py` family and similar round/version snapshots are examples of code that must not silently become parallel production owners. They require an explicit canonical/migration decision before further feature growth.

## Allowed dependency rules

- `kernel` may import only Python stdlib and other `kernel` modules.
- `api` and CLI adapters may import application/domain services.
- domain/application packages may import `kernel` and explicit lower-level contracts.
- domain/application packages must not import `skeleton.api`.
- UI/client code communicates through public contracts; it must not be a source of server authorization or trust policy.
- persistence, provider and tool adapters are injected behind contracts rather than imported into `kernel`.
- compatibility shims may depend on the canonical owner; the canonical owner must never depend back on its shim.

A dependency cycle is a defect even when Python can technically import it. If two packages need each other, extract the shared contract downward instead of adding lazy imports in both directions.

## Consolidation decision record

When promoting or replacing a subsystem, the PR must state:

- canonical owner and destination path;
- source implementation/repository and commit when mined externally;
- compatibility surface retained, if any;
- duplicate paths made experimental, frozen, or retired;
- migration/test evidence;
- any temporary boundary exception, with an owner and removal condition.

This keeps consolidation from becoming code accumulation without ownership.

## Enforcement roadmap

The executable guard intentionally begins small and fail-closed:

1. **Now:** keep the kernel free of framework/I/O dependencies and prevent domain-to-API reverse imports.
2. **Next:** add explicit package-edge rules after runtime, state, memory and tool contracts settle.
3. **Then:** add a duplicate-owner/provenance check tied to the repository inventory manifest.
4. **Finally:** treat the boundary check as a required merge gate once branch/ruleset administration confirms the check is enforced.

Do not broaden an exception list merely to make CI green. A new reverse dependency requires an architecture decision and, usually, extraction of a lower-level contract.
