# HyperForge Cockpit Absorption

Status: the native cockpit boundary now exceeds the source contract: secure host/guest control, auditable command receipts, canonical route publication and read-only WorldGraph revision/hash synchronization are absorbed.

## Source provenance

The source idea was mined selectively from `Apeloff1/hyperforge-cockpit-sota`, `main` tree `161c12634a2193e2b3024635205eac325d37fc8e`, primarily `src/lib/preview-host-bridge.ts`.

Skeleton does **not** import the source application's Vite/TanStack shell, authentication/database stack, Grok-specific branding, PWA assets, or deployment assumptions. The useful primitive is the hardened host ↔ preview control contract.

## Skeleton-native implementation

`frontend/src/cockpit/previewBridge.ts` provides a provider-neutral, Expo-web-compatible bridge with:

- versioned `skeleton-cockpit-bridge` envelopes;
- strict `event.source` and `event.origin` validation;
- same-origin parent support by default;
- explicit allowlisting for external parent origins;
- fail-closed behavior when no trusted parent can be established;
- relative same-origin navigation validation;
- host `hello`, `navigate`, bounded `history`, and read-only project-state request commands;
- bounded command `requestId` values and guest `command-result` execution receipts;
- explicit accepted/rejected status with stable rejection reasons;
- guest `location`, `routes`, `ready`, and canonical project-state publication;
- project-state validation for bounded project IDs, safe integer revisions and SHA-256 semantic hashes;
- explicit `writable: false` project-state publication so the bridge cannot become a world-mutation side channel;
- a history floor that prevents host Back commands from escaping the preview root;
- SPA `pushState` / `replaceState`, `popstate`, hash and project-state synchronization;
- deterministic disposal that restores patched history functions.

`frontend/app/_layout.tsx` wires the bridge to Expo Router and the canonical `ROUTE_REGISTRY`. Native and ordinary top-level web runs remain inert.

External deployment hosts may inject `globalThis.__SKELETON_COCKPIT_ORIGINS__` before application boot as either a comma-separated string or a string array. Only `http:` and `https:` origins are accepted.

Local product code publishes canonical state through `publishCockpitProjectState`; host messages cannot write that storage. The bridge normalizes and re-announces project state only after validation.

## WorldGraph synchronization

`backend/core/world_graph_projection.py` is the backend half of the contract. It builds a read-only projection from one canonical `WorldGraph` snapshot containing:

- project ID when supplied;
- graph revision;
- semantic SHA-256 hash;
- dirty/source metadata;
- aggregate node/edge counts for diagnostics;
- an explicit `writable: false` marker.

The cockpit state representation deliberately excludes nodes, edges, patch bodies and mutation capabilities. Writes remain on `WorldGraph.apply(WorldPatch)`, which requires the typed patch contract, graph revision and optional expected semantic hash. A cockpit can therefore detect stale preview state without gaining a bypass around the transactional world-edit boundary.

`backend/tests/test_world_graph_projection.py` proves that projection metadata changes after a canonical revision-gated patch while graph contents remain absent from the projection.

## Validation

`frontend/scripts/cockpit-bridge.test.mjs` exercises path/origin rejection, fail-closed external embedding, trusted route publication, navigation/history bounds, positive/negative execution receipts, project-state normalization, read-only publication, invalid state rejection and host request behavior. The zero-warning frontend workflow runs this contract on Node 24.

The convergence workflow separately exercises the backend WorldGraph transaction suite and read-only projection contract.

## Security invariants

1. A message is ignored unless it comes from `window.parent` and the resolved trusted parent origin.
2. Protocol channel and version must match exactly.
3. Navigation accepts only absolute-path references beginning with `/`; protocol-relative, cross-origin and backslash paths are rejected.
4. External parent origins are never trusted implicitly.
5. The bridge is disabled on native, server rendering and top-level browser execution.
6. History cannot be driven backward past the bridge's marked root entry.
7. Route publication comes from Skeleton's canonical registry rather than filesystem guesses or host-provided data.
8. Command receipts are emitted only for syntactically bounded request IDs from an already trusted parent message.
9. Rejected commands do not execute and carry a stable machine-readable reason when a valid request ID was supplied.
10. Project state can originate only from local application code, is schema-bounded before publication, and is always advertised read-only.
11. WorldGraph writes continue to require typed transactional patches; the cockpit bridge never accepts patch operations.

## Evolution path

This slice turns the cockpit from a separate UI repository into a reusable control-plane boundary inside Skeleton. Follow-on work should build on this protocol instead of copying the old application shell:

- capability-scoped host commands with explicit mutation/approval metadata, routed through existing application capabilities rather than direct preview writes;
- preview health plus Jeeves execution/admission evidence;
- operator-visible cancellation and budget state from the Jeeves execution kernel;
- reconnect/replay semantics for cockpit sessions;
- browser-level integration coverage beyond the pure protocol contract;
- durable project-state subscriptions that publish the new revision/hash only after canonical backend commits succeed.

The source repository remains intact; this is selective promotion, not history concatenation.
