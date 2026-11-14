# B038 + B039 AI generation provenance and bounded repair recovery

Source branch `archive/pre-rebase-gameforge-b039-20261113-61ec9b8a`.
The two original packages were absent from main as of 2026-11-13.

## Recovered modules
- `skeleton.gameforge.batch_b038`: hash-linked, content-addressed,
  source/transform/evaluation provenance and verifier.
- `skeleton.gameforge.batch_b039`: deterministic evaluation and diagnosis,
  router-receipt adapter, model/provider choice metadata, budgeted greedy
  repair and stable mutation receipts.

Both are offline-compatible and require **injected** evaluator, proposer,
router and clock functions. They do not call external providers, download
weights, execute generated Python, or publish unaudited artifacts.
The existing production GameForge ten-stage engine is not overwritten.

## Hardened source
Historical B039 accepted NaN/Infinity budget and mutation cost values,
which could bypass `max_cost` comparisons. The recovered contract now
rejects non-finite/negative time and cost budgets, nonfinite evaluator
scores, unsafe route/proposal spend, and non-monotonic/invalid clocks.
Focused regressions accompany the original tests.

## Remaining integration
These are **libraries**, not an enabled autonomous repair job. A project
identity, reviewed candidate diff, provenance seal, exact model custody,
security gates and rollback must be supplied before wiring automatic
mutations to the main engine or Jeeves.

Focused qualification:
`python -m pytest -q skeleton/gameforge/batch_b039/test_self_repair.py skeleton/gameforge/batch_b039/test_route_adapter.py skeleton/gameforge/test_gameforge_conductor.py backend/tests/test_historical_gameforge_preview.py`

Full exact-head CI, security, source-parity and native qualification remain
independent merge holds.
