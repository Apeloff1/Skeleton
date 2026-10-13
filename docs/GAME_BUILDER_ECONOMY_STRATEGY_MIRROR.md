# Original Economy: Strategy Mirror and Counterfactual Knowledge

Status: draft implementation. Date: 2026-10-12 (UTC date).

## Operational milestone

The original trade game now runs alternative original market decisions through
the same finite deterministic source engine, then independently replays and
compares their **actual simulated consequences**. It cannot mutate project
files, publish model weights, invent profitable opportunities or call an
incomplete search optimal.

Policies cover passive demand, finite harvesting, ore-to-tool manufacturing,
recovery, household treasury relief, physical adjacent trade and imports,
audited deliveries, achieved cooperation and different goods strategies.
Every attempted alternative consumes resources, demand and player cash just
as the real game would.

A relative scoring rule identifies a policy for user consideration while the
Pareto frontier separately displays trade-offs among household consumption,
production, imports, household liquidity, remaining finite reserves and player
cash. **The score is not a forecast, source truth or weight-promotion proof.**

## Rigorous evidence

- Exact authored source digest, typed editor settings, seed and turn horizon.
- Maximum 40 scenarios and at most 48 economy turns per scenario.
- Record both feasible simulations and all infeasible original actions.
- Full cash conservation across player, household and market treasury.
- Physical stock accounting for reserve harvest, finite ore conversion,
  household consumption and player cargo.
- Exact replayed original game-state digest and chained transcript digest
  for every accepted counterfactual.
- Explicit partial-search status and unmodeled catalog families.
- No weights promoted, no native hardware verified, no project writes.

## Actual user workflow

The existing local Studio Economy panel gains a market mirror comparison
action. Reviewed scenes yield a source-proof table showing real consumption,
imports, output, player balances, treasury and deltas versus a passive market
over the same horizon.

The user may explicitly choose a verified alternative and adopt it only from
an unchanged original world. The Studio verifies the entire evidence receipt
again and replays the source through actual economic gameplay. The final
session digest must match the selected original outcome. User approval is
required and native project files remain unchanged.

Offline CLI: economy-mirror and verify-economy-mirror, both requiring a
reviewed --scene file.

## Code and cross-platform validation

- skeleton/ai/game_builder/advanced_economy_mirror.py
- tests/test_game_builder_advanced_economy_mirror.py
- skeleton/ai/game_builder/system_editor_cli.py
- skeleton/ai/game_builder/game_workspace_server.py
- skeleton/ai/game_builder/game_workspace_ui.py
- .github/workflows/game-builder-advanced-system-engines.yml

Tests target independent replay, finite cash and inventory, source custody,
different economy sizes, accepted and refused actions, limited-budget reports,
Pareto nondominance and tampered source/scoring/history rejection.

## Timestamped history

- 2026-10-12 — multi-policy economic scenarios (added real household,
  producer, import and civic choices rather than prewritten conclusions).
- 2026-10-12 — economic conservation and chained game receipts (improved
  scrutiny of material and monetary accounting).
- 2026-10-12 — Pareto comparison and incomplete-search flags (improved
  multi-objective honesty and transparency).
- 2026-10-12 — offline CLI and supervised Studio UI (added audited alternative
  review and explicitly player-approved replay adoption).
- 2026-10-12 — adversarial regression coverage (rejects forged cash, score,
  actions, sessions, source swaps and out-of-range budgets).

## Dependencies and limitations

This implementation depends on original native Economy draft #3669, reference
Economy draft #3668 and root Game Studio draft #3642. No parent is implicitly
merged; actual hosted exact-head CI is required before a merge. Native
counterfactual parity, model weight changes, commercial markets, hardware
certification and fully completed applications are outside this milestone.
