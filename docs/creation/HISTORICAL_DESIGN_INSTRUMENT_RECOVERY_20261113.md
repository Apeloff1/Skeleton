# Historical GameForge design controls — source-preserving recovery

This is an implementation slice, not an entire historical-repository merge.
Source inspected on 2026-11-13: Skeleton main, Prood main, Skeleton archive
pre-rebase branches, and historical merged pull requests.

## Recovered design path

- Skeleton #3754 and #3755: questionnaire intake, persistent CLI operator
  steering, and a ten-stage GameForge engine. Previously merged to main.
- Skeleton #4203 and #4204: Jeeves native multi-facet questionnaires and
  38 production-facet runbook flows. Previously merged to main.
- Skeleton #4116 and #4124: accessible Forge questionnaire, plan, era, run
  journey and studio handoff. Previously merged to main.
- Apeloff1/Prood/frontend/components/DeepSlider.tsx: fine-grained horizontal
  slider with tier readout, touch movement and +/- bumps. UX principles adapted
  here to Skeleton's existing UI primitives and canonical theme tokens.
- Skeleton archive/pre-rebase-quiz-bank-20261113-a7a5f3aa contains a school
  quiz bank, not the canonical GameForge game-design questionnaire; preserve it
  separately and do not accidentally replace the creator brief.
- Skeleton archive/pre-rebase-gameforge-conductor-20261113-8e20778a is older
  and divergent from current main's production GameForge engine. Review by
  individual module, not a wholesale merge over a newer engine.

## Implementation

The existing Options step of /skeleton-forge now contains an optional ten-axis
design instrument panel. A touched axis is an explicit override; an untouched
axis is NOT a default 0.5 and remains derived from the existing
questionnaire/era resolver. Fine-grained touch and accessible +/- adjustments
edit client draft values. Reset per-axis or all axes restores automatic mode.

The sparse operator_axes mapping flows through the existing /api/skeleton/run
request and canonical GameForgeRun.execute pipeline, applying AFTER the
questionnaire intake, era and historical operator_tensor precedence. The
run response can show the exact accepted overrides alongside the final tensor.
All values are checked for known axes, finite numeric type and unit range.

No unauthenticated global server cockpit or cross-project shared axis state is
introduced: the old /api/skeleton/cockpit endpoint constructs a new Cockpit
per request. That endpoint's command continuity is a separate existing defect,
not falsely claimed fixed by these per-run controls.

## Follow-on integrations still required

1. Replace ephemeral cockpit commands with authenticated per-project
   revision-checked durable steering and audit receipts; never persist runtime
   secrets or inference context in a project preference.
2. Reconcile Prood's other creative knobs/genre/asset style pickers and
   selected archive branches against the modern canonical editor contracts.
3. Unify Jeepes/Jeeves creation runbook, 38 facets, asset generation, world
   editor, quest/story composition, GameForge execution and Godot acceptance
   around explicit project IDs and approved writes.
4. Require exact-head full frontend, backend, security and native
   device/Godot tests before main integration or release claims.
