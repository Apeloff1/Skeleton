# Frontend lint and long-session stability

The canonical lint configuration is [eslint.config.js](eslint.config.js)
(ESLint 9 flat config, Expo). The frontend pins `eslint` and
`eslint-config-expo` in `package.json`; do **not** use unpinned
`npx -y` commands or a stale `.eslintrc.cjs` recipe.

From `frontend/`, with the project dependencies installed:

```sh
yarn lint:ci
yarn typecheck
yarn test:stability
yarn test:stability:reconciliation
```

The stability suite includes deterministic Node regression tests for boot
recovery, request retries, storage retention, thermal queue saturation and
liveness, battery listeners, recovery single-flight behavior, session progress
ordering/coalescing, storage hydration, authenticated request isolation,
bounded network responses, scoped health polling, push notification teardown,
and timer cleanup. It does not replace
on-device endurance, installed-app E2E, or native lifecycle testing.

## Incremental lint debt retirement

The broader app still has pre-existing React Hooks lint debt. We do not
turn every legacy violation into a build blocker or suppress every rule
globally without accounting for it. The battery, thermal, and recovery
modules now opt back into `react-hooks/exhaustive-deps` and
`@typescript-eslint/no-unused-vars`. Future migrations should expand
that list only after fixing the affected hooks and adding lifecycle
regressions. Do not disable `react-hooks/rules-of-hooks`.

## Operational invariants

- Native listeners acquired after an async initialization step must be
  cancelled if the component unmounted while awaiting the device.
- A React state updater cannot call another state setter.
- Device observations should not be fabricated or replaced when another
  sensor sends a partial update; unknown battery readings are ignored.
- Queued work must settle after synchronous callback failures, and
  cancelled delayed work must not execute side effects.
- Background throttling survives thermal recalculation and cooldown.
- Recovery runs are single-flight, bounded, and do not update unmounted UI.

For a release verdict, also run the complete app and backend checks,
first-install checks, and a real multi-hour device exercise. Passing lint,
unit tests, or TypeScript compilation alone does not prove long-session
stability.

## Focused pull-request gate

The existing `Merge Readiness` workflow runs
`node --test scripts/test-long-session-stability.cjs` with an isolated
TypeScript transpilation dependency. This adds no workflow and does not
require the full Expo install. It is a focused runtime contract regression,
not a substitute for `yarn typecheck`, `yarn lint:ci`, the installed
application, or endurance/pressure E2E.

## Marathon pressure regressions (network and thermal)

The existing fast Merge Readiness job additionally runs
`scripts/test-marathon-pressure.cjs` beside the lifecycle suite; no new
workflow is created. The pressure suite checks explicit read-only
coalescing, non-coalesced writes, cache memory admission, streaming response
budgets, request-format isolation, safe fallback behavior for requests
with custom headers, reset fencing, and thermal observer failure isolation.

These checks are deterministic simulations. Release qualification still
requires `yarn typecheck`, `yarn lint:ci`, a real native install and
sustained device monitoring. A response body adapter that exposes only
`.text()` cannot be prevented from buffering its full body internally;
it is rejected after materialization if oversized. Streaming adapters
enforce the limit before full buffering.
