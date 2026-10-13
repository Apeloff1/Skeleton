# Jeeves Story Continuity Workbench — creator-owned evidence

The world project link `/story-index?game=<id>` opens a real game-scoped,
branch-scoped continuity ledger. Its canonical backend routes are registered
through `backend/core/routes_registry.py` at
`/api/playable/{pid}/story-index`.

The read-only screen loads paginated event evidence, audits story logic,
shows unresolved promises and recall with evidence citations, and can hand
the selected character's source context to Jeeves without overwriting a
pending user handoff.

Editors can now append creator-reviewed events from the same screen,
using `frontend/src/product/storyContinuity.ts` for bounded validation.
Event IDs remain stable; exact repeat requests are idempotent, while reuse
with altered content is rejected by the server. Event kinds include dialogue,
witnesses, discovery, promises and resolutions, deaths and revivals.
Character witnesses must be actual participants; a dialogue must name its
speaker, and a promise/resolution must have a thread identity. Act, scene,
and beat numbers are bounded. Required/granted knowledge references are
tracked without claiming they have been independently verified.

The server authenticates all reads and writes, enforces editor capability
for writes, keeps each tenant/owner/game/branch separated, checks that
the canonical game knowledge base already exists, and retains source
integrity as `creator_supplied_not_independently_verified`.
Nothing in this screen automatically promotes stories to permanent
model weights, invents NPC memories, or silently marks plot threads
resolved. Audit truncation remains visibly incomplete.

Regression:
`cd frontend && node --test scripts/test-story-continuity.mjs`
and `yarn typecheck`, alongside backend story index registration tests.
