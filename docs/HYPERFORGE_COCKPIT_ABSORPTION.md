# HyperForge Cockpit Absorption

Status: first native integration slice landed on the Jeeves evolution branch.

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
- host `hello`, `navigate`, and bounded `history` commands;
- guest `location`, `routes`, and `ready` state publication;
- a history floor that prevents host Back commands from escaping the preview root;
- SPA `pushState` / `replaceState`, `popstate`, and hash synchronization;
- deterministic disposal that restores patched history functions.

`frontend/app/_layout.tsx` wires the bridge to Expo Router and the canonical `ROUTE_REGISTRY`. Native and ordinary top-level web runs remain inert.

External deployment hosts may inject `globalThis.__SKELETON_COCKPIT_ORIGINS__` before application boot as either a comma-separated string or a string array. Only `http:` and `https:` origins are accepted.

## Security invariants

1. A message is ignored unless it comes from `window.parent` and the resolved trusted parent origin.
2. Protocol channel and version must match exactly.
3. Navigation accepts only absolute-path references beginning with `/`; protocol-relative, cross-origin, and backslash paths are rejected.
4. External parent origins are never trusted implicitly.
5. The bridge is disabled on native, server rendering, and top-level browser execution.
6. History cannot be driven backward past the bridge's marked root entry.
7. Route publication comes from Skeleton's canonical registry rather than filesystem guesses or host-provided data.

## Evolution path

This slice turns the cockpit from a separate UI repository into a reusable control-plane boundary inside Skeleton. Follow-on work should build on this protocol instead of copying the old application shell:

- capability-scoped host commands with explicit mutation/approval metadata;
- preview health and execution-evidence events;
- WorldGraph revision/hash synchronization for editor previews;
- operator-visible admission/cancellation state from the Jeeves execution kernel;
- reconnect/replay semantics for cockpit sessions;
- browser contract tests and a dedicated cockpit convergence gate.

The source repository remains intact; this is selective promotion, not history concatenation.
