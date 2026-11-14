# GameForge archived conductor and B039 runtime convergence

Parent integration: PR #5318 at
`e5bac632530ce407343644907d06b12f0a78d957`.
Original historical main-target recovered preview: PR #5299 at
`6f3cdf51e8f3ff46079b3a1d6e0c2ec5b182a7e1`.
Latest independently hardened conductor/B039 source: PR #5293 at
`bb409ddcce46c3dec1170f35ad99cb7d9f587631`.

## Recovered native behavior

- All seven deterministic conductor stages: vision, snowball, prototype,
  mass forge, world, cockpit, export. Original stage ordering, era custody,
  manifest integrity, bounded artifact budgets and safety checks retained.
- B039 bounded diagnosis/repair loop with capability routing and provenance,
  using #5293's newer nonfinite/cost/clock/mutation hardening and its own
  matching focused regressions. It is not permitted to issue unlimited edits.
- The new API `POST /api/skeleton/conductor/preview` is additive, opt-in,
  bounded to 1 MB/20 regions/5 short pillars, and returns only receipts,
  stage completion, manifest and artifact names/aggregate bytes. No files
  are written and no generated code is executed in this preview endpoint.
- The guided GameForge questionnaire now has a separate collapsible
  seven-stage preview panel, with explicit choice of eight historical
  conductor families and no automatic preview until the user clicks.
- The 158 selectable creator genres, original Galaxy questionnaire,
  ten-axis knobs and build request, Jeeves interactive game builder,
  Frontier runtime and Godot export source are left intact. Eight
  conductor planning families are not a claim of 158 playable engines.

## Source provenance

Seventeen tracked source/test/docs/workflow files were retained as original
Git blobs from #5299 and the later hardened B039 #5293. The shared
`backend/routes/skeleton_gameforge.py` was reconciled by additive insertion;
no historical wholesale replacement of the modern pipeline. The optional
frontend panel and frontend route client are new, small compatibility
adapters. No provider key, network agent or expanded build authority added.

## Required final-head qualification

```sh
PYTHONPATH=.:backend PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest --noconftest -q \
  skeleton/gameforge/test_gameforge_conductor.py \
  skeleton/gameforge/batch_b039/test_self_repair.py \
  skeleton/gameforge/batch_b039/test_route_adapter.py \
  backend/tests/test_historical_gameforge_preview.py \
  tests/test_forge_gameplay_design.py \
  tests/test_forge_interactive_runtime.py
cd frontend && node --test scripts/skeleton-forge/conductor-preview.test.cjs scripts/skeleton-forge/controls-preview.test.cjs
cd frontend && yarn typecheck
```

Dedicated `GameForge seven-step conductor and B039 repair tests` GitHub
Action retains pinned commits and read-only permissions. The root exact-head
CI, source/mirror, security, malware, hygiene, artifact, native Godot,
Windows/WSL2, local Jeeves and first-install gates remain mandatory.

No merge/auto-merge/release/first-install approval until required
final-head evidence is successful. Skipped/cancelled/queued/ancestor runs
do not qualify.
