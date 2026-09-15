# Canonical Module Boundaries

This document is the consolidation ownership contract for Skeleton. It complements `docs/ARCHITECTURE.md` by naming the canonical home for each subsystem and the dependency directions that new code must preserve. When historical documents describe older layouts, this contract controls consolidation decisions.

## Canonical ownership

| Capability | Canonical owner | Boundary |
| --- | --- | --- |
| Domain/runtime primitives | `skeleton/` | Reusable product logic lives here and must not depend on the application, UI, or test trees. |
| Kernel vocabulary | `skeleton/kernel/` | Errors, events, identifiers, registries, and other inward-facing primitives. |
| Agent orchestration | `skeleton/agents/`, `skeleton/jeeves/` | Agent, tutoring, provider, and session semantics. Do not create a second agent runtime under `backend/`. |
| Durable execution state | `skeleton/state/` | Provider-neutral run/checkpoint persistence and migration contracts. |
| Memory / RAG | `skeleton/jeeves/` and other promoted `skeleton/` memory primitives | Reusable retrieval and memory behavior belongs in the library layer; application adapters may consume it. |
| Consolidated/mined primitives | `skeleton/frontier/` after promotion; `skeleton/acquired/` only as lineage/staging | A promoted capability gets one canonical implementation. Staging copies must not become a competing runtime. |
| Forge / game / world policy | `skeleton/forge/`, `skeleton/frontier/` | Portable policy and domain behavior. Engine/application integration belongs below the application boundary. |
| GameForge application adapters | `backend/gameforge/` | Process, storage, HTTP, engine, and deployment adapters may import `skeleton`; `skeleton` must never import them. |
| HTTP application and routes | `backend/` | `backend/server.py` and backend routes are the canonical deployed FastAPI application boundary. `skeleton/api/` may contain reusable API helpers, but must not become a second deployed application bootstrap. |
| CLI | `skeleton/__main__.py`, `skeleton/developer/` | Reusable command entry points and developer tooling. |
| UI | `frontend/` | User-interface code consumes backend contracts; Python runtime code must not import UI modules. |
| Canonical tests | `skeleton/testing/`, `backend/tests/` | Tests may depend on production code. Production code must never depend on test packages. |
| Historical root harnesses | `tests/legacy_root/` | Archive/manual evidence only. Do not restore these files to production or canonical test discovery. |

## Dependency direction

The coarse dependency direction is:

```text
frontend  ->  backend  ->  skeleton
                        ->  external adapters

tests     ->  production code
```

The arrows mean "may depend on." Reverse dependencies are forbidden at the repository boundary:

- production code under `skeleton/` must not import `backend`, `frontend`, or the root `tests` namespace;
- production code under `backend/` must not import `frontend`, the root `tests` namespace, or `skeleton.testing`;
- test trees are consumers and may import production surfaces for fixtures and integration checks;
- relative imports within a canonical package remain governed by that package's internal architecture;
- adding a bridge to bypass these directions requires moving the abstraction inward, not adding an allowlist exception.

These rules intentionally start with high-confidence repository boundaries rather than attempting to freeze every internal package relationship. Tightening them later should be paired with migrations and regression tests.

## Duplicate implementation decisions

Consolidation must end with one owner per capability. The following decisions are explicit:

1. **Deployed API bootstrap:** `backend/` owns the running FastAPI application. Reusable helpers under `skeleton/api/` are library code, not a second server composition root.
2. **Root test harnesses:** `tests/legacy_root/` is archive-only. New regressions belong in `skeleton/testing/` or `backend/tests/` according to the code they validate.
3. **Mined code:** `skeleton/acquired/` may preserve source lineage while work is evaluated. Once behavior is promoted, the canonical target package owns it; do not maintain a parallel production implementation in acquired/staging code.
4. **Agent/Jeeves behavior:** reusable session, provider, tool-capability, and orchestration semantics belong in `skeleton/agents/` or `skeleton/jeeves/`. Backend code should adapt those contracts rather than reimplement them.
5. **Game/world policy:** portable policy belongs in `skeleton/forge/` or `skeleton/frontier/`; `backend/gameforge/` owns application and engine integration only.

When two implementations are discovered, the merge decision must be one of: promote one and delete/archive the other, transplant the unique invariant into the canonical owner, or retain the second implementation only as a clearly non-production compatibility/lineage fixture. "Keep both active" is not a consolidation outcome.

## Executable enforcement

`backend/scripts/check_architecture_boundaries.py` is the executable minimum contract. It uses the Python AST rather than text matching, fails closed on unreadable or unparsable production Python files, and scans the canonical `skeleton/` and `backend/` roots.

Backend Quality runs the checker and its focused regression suite. Any future expansion of the boundary policy must add tests for both rejected imports and legitimate imports so the gate remains precise rather than becoming an exception list.
