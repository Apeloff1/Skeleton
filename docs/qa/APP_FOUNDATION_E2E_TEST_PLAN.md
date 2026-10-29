# App Foundation E2E Test Plan

Owner: Carrol (QA Director). Runner: Shirt 1 (QA IC, functional and regression).
Suite: `frontend/scripts/test-app-foundation-flows.mjs` (repo-native `node --test`, Node >= 24).
Gate: G-E2E in `docs/qa/REGRESSION_GATES.md`. Any red Sev1 or Sev2 case is NO-SHIP.

## Scope

The five core flows a new player hits on day one:

| Flow | What the player does | Routes | Backend contract |
|---|---|---|---|
| F1 Onboarding | First launch, welcome splash, land in the product shell, start the first journey | `/`, `/welcome`, `/setup`, `/product`, `/hub` | `GET /api/app/bootstrap`, `GET /api/app/status` |
| F2 Sign-in | Register or sign in with email, or continue with Google; session survives reload; bad password rejected | `StudioLoginGate` on gated routes | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/session`, `POST /api/auth/logout` |
| F3 Create project from brief | Describe the game, generator hands off to Game Factory, a build is created | `/ai-game-generator`, `/game-factory`, `/galaxy` | `POST /api/galaxy-studio/create`, `POST /api/galaxy-studio/start-build` |
| F4 Watch build | Progress updates while building; terminal success or failure shown honestly; leaving the screen does not cancel | `/studio`, `/galaxy` | `GET /api/galaxy-studio/status/{build_id}` |
| F5 Open result | New build appears in the library; Open resumes it; build-scoped steps deep-link to it | `/my-builds`, `/galaxy`, `/game-kb`, `/playable` | `GET /api/galaxy-studio/my-builds` |

Out of scope here: APK/EAS export, deploy, multiplayer, and the standalone-AI lanes (covered by `STANDALONE_AI_E2E_TEST_PLAN.md`).

## Tiers

**Tier 1, contract (runs everywhere, no backend).** Asserts the routes exist, the screen sources keep their flow wiring (welcome flag and redirect, auth endpoints, fail-closed sign-in, generator handoff, library open), and drives the real pure modules (`journeyCatalog.ts`, `buildJobLifecycle.ts`) through each flow. Runs in CI via `yarn test:product-journeys` (Frontend job) and alone via `yarn test:app-foundation`.

**Tier 2, live (opt-in).** With `SKELETON_E2E_BASE_URL` set, one test drives the real backend over HTTP: bootstrap, register, sign in, verify `/me`, reject a wrong password, and verify that public registration grants only the viewer role and cannot create builds. A bounded three-file build, observation with the production `watchBuildJob`, and retained-partial library verification additionally require `SKELETON_E2E_OPERATOR_TOKEN_FILE` pointing to a private file containing a valid editor/admin token. The test requires enforced authentication and never upgrades the public consumer account. Its three-file ceiling intentionally stops the mandatory pipeline: it verifies `artifact_file_budget_exhausted`, exactly three durable files, no fabricated completed phases, and fully drained workers. This is a bounded install and recovery probe, not successful end-to-end game creation. `SKELETON_E2E_MAX_CHECKS` bounds the watch (default 120). The live suite is skipped when the base URL is unset; build mutation steps are skipped when the private operator token file is absent.

**Tier 3, browser (planned).** Playwright against `yarn export:web` output, using the existing `testID`s (`gate-email`, `gate-pass`, `gate-submit`, `gate-error`, `gate-google`). Not added yet because it needs new dependencies and a `yarn.lock` regeneration; tracked as a follow-up. Until then Shirt 1 covers the UI layer manually with the cases below.

## Cases

| ID | Flow | Case | Tier | Sev if red |
|---|---|---|---|---|
| F1-01 | Onboarding | Entry routes exist: index, layout, welcome, setup, product, hub | 1 | Sev1 |
| F1-02 | Onboarding | Welcome stores `@codedock:welcome_seen:v1` and lands on `/product`; auto-advances if untouched | 1 | Sev2 |
| F1-03 | Onboarding | First journey is `idea-to-game`, starts at the brief, every step route exists | 1 | Sev2 |
| F1-04 | Onboarding | Bootstrap returns an application name | 2 | Sev1 |
| F1-M1 | Onboarding | Manual: cold launch on web shows welcome once, never again after reload | manual | Sev2 |
| F2-01 | Sign-in | Client calls only the canonical `/api/auth/*` endpoints | 1 | Sev1 |
| F2-02 | Sign-in | Tokens never stored in AsyncStorage; SecureStore on native | 1 | Sev1 |
| F2-03 | Sign-in | 401 clears the session; unverifiable `/me` fails closed | 1 | Sev1 |
| F2-04 | Sign-in | Gate shows "unavailable" when `/me` is unverified and never renders gated content | 1 | Sev1 |
| F2-05 | Sign-in | Register, sign in, `/me` authenticated, wrong password rejected | 2 | Sev1 |
| F2-M1 | Sign-in | Manual: email sign-in, reload keeps session, logout clears it | manual | Sev1 |
| F2-M2 | Sign-in | Manual: Google sign-in completes the web redirect and strips `session_id` from the URL | manual | Sev2 |
| F3-01 | Create | Generator hands off to `/game-factory` with the generated artifact | 1 | Sev1 |
| F3-02 | Create | Build-accepting steps only carry safe ids (path traversal, spaces, markup, oversize rejected) | 1 | Sev1 |
| F3-03 | Create | Create from brief returns a safe `build_id`; start-build accepted | 2 | Sev1 |
| F3-M1 | Create | Manual: type a brief, generate, see Game Factory open with it | manual | Sev1 |
| F4-01 | Watch | `building` is pending; `completed` with an error is failure; `failed` is failure | 1 | Sev1 |
| F4-02 | Watch | building, building, completed reports progress twice then success | 1 | Sev2 |
| F4-03 | Watch | Repeated status outages show "disconnected, may still be running", never success or failure, never leak hostnames | 1 | Sev1 |
| F4-04 | Watch | Leaving the screen stops polling and says the backend build was not cancelled | 1 | Sev2 |
| F4-05 | Watch | Live build reaches `completed` within the check budget | 2 | Sev1 |
| F4-M1 | Watch | Manual: progress visibly updates; kill the backend mid-build and see the disconnected state, not a spinner | manual | Sev2 |
| F5-01 | Open | Library reads `/api/galaxy-studio/my-builds`; Open stores the active build and resumes `/galaxy` | 1 | Sev1 |
| F5-02 | Open | Knowledge step locked without a build, deep-links `/game-kb?game=<id>` with one | 1 | Sev2 |
| F5-03 | Open | Every journey step in the core shell resolves to a shipped route | 1 | Sev2 |
| F5-04 | Open | New build appears in the library | 2 | Sev1 |
| F5-M1 | Open | Manual: Open on the new build resumes it in Galaxy Studio and the result is playable on `/playable` | manual | Sev1 |

## How Shirt 1 runs it

1. Tier 1: `cd frontend && yarn install --frozen-lockfile && yarn test:app-foundation`. All cases pass, the live case reports skipped.
2. Tier 2: start the stack (backend on `:8001` with Mongo), then `SKELETON_E2E_BASE_URL=http://localhost:8001 SKELETON_E2E_OPERATOR_TOKEN_FILE=/private/path/operator-token yarn test:app-foundation`. Record the `watch outcome` diagnostic line.
3. Manual: `yarn web`, run every `-M` case in a fresh browser profile.
4. File each red case as a GitHub issue titled `[QA][F<n>-<id>] <case>` with severity, repro steps, expected vs actual, and the commit SHA. Sev1/Sev2 block rollout until fixed and re-verified.
5. Report the run (SHA, tier results, issues filed) to Carrol.

## Known findings at authoring time

- `scripts/test-build-job-lifecycle.mjs` "backend disconnect" asserted `failed`, but `watchBuildJob` deliberately reports outages as `disconnected` (or `timeout` when the check budget runs out first). The test was red and hidden because `yarn lint:ci` fails earlier in the Frontend job. Fixed in the same PR as this plan.
- The Frontend CI job is red on `yarn lint:ci` on main, so test steps after it, including this suite, do not run in CI until lint is green. Tracked under G-FE.
