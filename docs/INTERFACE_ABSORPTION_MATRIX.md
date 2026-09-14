# Interface Absorption Matrix

The product is converging on one application with canonical capability domains. Historical projects are not preserved as separate applications by default; they are mined for useful behavior, redesigned against current primitives, and absorbed into shared workspaces.

The executable ledger lives in `frontend/src/workspaces/legacyMap.ts`. The UI view lives at `frontend/app/migration-map.tsx`.

## Canonical domains

| Domain | Canonical route | Primary absorbed systems |
| --- | --- | --- |
| Jeeves Operator | `/jeeves-control` | assistant shell, model/API routing experiments, agent control |
| Work OS | `/workforce` | clock in/out, focus, pauses, worker time logs |
| Market Intelligence | `/market-intelligence` | stock assistant, RSS analysis, tick-chart experiments |
| Wealth & Progress | `/wealth` | hours-vs-profit, fantasy coins, milestones |
| Collaboration | `/collab` | worker/admin messaging, freelancer scheduling, task status |
| Vault | `/vault` | bookmarks, durable references, secure-link boundary |
| Learning | `/dashboard` | booklets, reading, curriculum, tutoring experiments |
| Creation Studio | `/gameforge-studio` | games, WordPress tooling, desktop builders, media generation |
| System Control | `/command-center` | admin dashboards, API/runtime panels, diagnostics |

## Migration states

### `absorbed`
The capability has a canonical destination and the new application already contains a real replacement surface or primitive. This does **not** mean byte-for-byte feature parity with the old implementation; it means the useful behavior has an owned destination and working implementation.

### `evolving`
A canonical destination exists and active implementation is present, but the behavior is still being expanded, hardened, or consolidated.

### `queued`
The capability is intentionally tracked but not yet represented as completed. Queued capabilities remain visible so mining work cannot silently disappear.

### `retired`
The historical behavior should not be rebuilt as-is. Retired rows must name a replacement boundary or explain why the pattern is unsafe, redundant, obsolete, or architecturally incorrect.

## Risk levels

`low` covers local or presentation-oriented behavior with a narrow failure radius.

`medium` covers shared state, persistence, integrations, scheduling, generated artifacts, or behavior where migration mistakes can create meaningful product inconsistency.

`high` covers credentials, authorization, financial/market claims, provider routing, broad administrative visibility, destructive mutation, or other sensitive control-plane behavior.

Risk is not a completion score. It determines the validation and approval burden of the migration.

## Absorption rules

1. **Mine behavior, not files.** Old repositories are evidence of desired behavior, not templates that must survive unchanged.
2. **One canonical destination.** Each migrated capability has one owning workspace even if Jeeves can invoke it from elsewhere.
3. **No duplicate control planes.** Runtime health, model/provider configuration, diagnostics, builds, safety, and agent operations converge on System Control.
4. **No duplicate assistant shells.** Jeeves becomes the operator across capabilities; feature-specific assistant screens are specialist views, not independent products.
5. **No decorative truth.** Prices, runtime health, agent counts, provider state, build status, and other operational facts must come from real data sources or be labeled unavailable.
6. **No ad-hoc credential system.** The historical shared-password-folder idea is retired. Vault may hold secure references, but secrets require trusted secure storage and explicit authorization boundaries.
7. **Preserve provenance.** Research, market evidence, generated assets, and imported references retain source metadata where available.
8. **Typed mutation.** High-risk actions declare required approval, scope, evidence, and rollback behavior before they are exposed to operator automation.
9. **Shared primitives first.** Timers, ledgers, tasks, messages, references, projects, telemetry, and model routing should be implemented once and reused.
10. **Migration state stays explicit.** A screen or route is not called live merely because a placeholder renders.

## Historical interface mapping

| Historical interface or experiment | Useful behavior | Destination | Current intent |
| --- | --- | --- | --- |
| Jeeves desktop assistant | conversation, analysis, assistant orchestration | Jeeves Operator | evolve |
| OpenAI/API key switcher experiments | provider selection | Jeeves Operator + System Control | replace with policy-driven routing |
| Stock assistant | watchlists, analysis, source-backed decisions | Market Intelligence | evolve |
| RSS market analyzer | source ingestion | Market Intelligence | queue behind provenance ledger |
| Tick predictor experiments | tick visualization and historical comparison | Market Intelligence | migrate visualization; reject unsupported prediction certainty |
| Clock-in/out desktop app | work sessions | Work OS | evolve into session ledger |
| Pause menu | break state | Work OS | normalize into typed pause intervals |
| Worker/admin tracker | role-scoped team visibility | Collaboration | migrate only with authorization boundaries |
| Worker status messages | execution communication | Collaboration | absorbed |
| Freelancer scheduler | tasks, schedules, deadlines | Collaboration | evolve |
| Hours-vs-profit app | measured work vs entered value | Wealth & Progress | evolve |
| Fantasy coin system | motivational economy | Wealth & Progress | evolve and make configurable |
| Shared bookmark folder | durable links and references | Vault | absorbed |
| Shared password folder | credential storage | Vault boundary | retire ad-hoc implementation |
| Learning booklets | structured reading | Learning | absorbed into curriculum surfaces |
| Assistant tutor experiments | contextual tutoring | Learning | evolve through Jeeves |
| Tamagotchi dinosaur game | lifecycle simulation | Creation Studio | queue as reusable game template |
| WordPress utilities | content/site/build tooling | Creation Studio | decompose into explicit tools |
| Desktop GUI builders | app project generation | Creation Studio | evolve |
| Admin dashboards | system oversight | System Control | absorbed |
| Runtime diagnostics | logs, health, telemetry | System Control | absorbed |

## Definition of absorbed

A capability can move to `absorbed` only when all of the following are true:

- the canonical owner is named;
- the destination route exists;
- user-facing behavior is backed by a real primitive, store, service, or verified data source;
- persistence behavior is defined when state must survive restart;
- permissions are explicit where data spans users or roles;
- failure and empty states are represented;
- old duplicate entry points are either redirected, clearly marked specialist/legacy, or removed;
- the migration ledger row documents the replacement.

## Next mining priorities

1. Finish Work OS persistence for clock/pause/session behavior.
2. Move market ingestion to a provenance-first source ledger before expanding analysis automation.
3. Consolidate provider/model controls behind Jeeves policy routing and System Control observability.
4. Expand Collaboration with role-scoped task and schedule primitives before porting broader admin views.
5. Convert Creation Studio legacy projects into project templates instead of dedicated legacy screens.
6. Continue retiring duplicate navigation and specialist dashboards after their capabilities have canonical replacements.
