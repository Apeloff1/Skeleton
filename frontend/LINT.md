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

The stability suite includes deterministic Node regression tests for
boot recovery, request retries, storage retention, thermal queue liveness,
battery listeners, and recovery single-flight behavior. It does not replace
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
