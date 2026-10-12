# Original Trading Economy — Advanced Reference Milestone

Status: **draft engineering implementation**, 12 October 2026. This is an
original deterministic playable reference, **not** a simulated stock exchange,
scientific economic forecast, licensed game, native Godot economy, or production
platform certification.

## Deliverable: 30th playable editor family

Trading & Economy gains a real authored source-backed reference runtime on top
of existing deterministic game session infrastructure. Once its stacked PR is
integrated, 30 of 43 system families have original playable reference engines.
The other 13 remain authoring-only; total app completion is not being claimed.

Source files:
- skeleton/ai/game_builder/advanced_economy_runtime.py
- skeleton/ai/game_builder/advanced_gameplay_runtime.py
- skeleton/ai/game_builder/advanced_level_scenes.py
- skeleton/ai/game_builder/system_editors.py
- tests/test_game_builder_advanced_economy.py
- .github/workflows/game-builder-advanced-system-engines.yml

### Real deterministic gameplay

Worlds support up to 16 embodied markets and up to 8 actively playable goods.
The remaining editor-configured market nodes and product families are explicitly
marked *unmodeled*, not deceptively counted as independently simulated agents.

Markets run real, bounded turns:
- Finite region resource harvesting and ore-to-tool manufacturing consume
  material, warehouse capacity and finite labor energy.
- Source-defined local inventories, household and treasury accounts and real
  purchasing power remain conserved by actor-to-actor payments.
- Household food and goods demand uses actual stock and finite household
  money. Price changes respond to supply, bounded within authored limits.
- Physical transport requires adjacent travel, freight capacity and fares.
  Cargo preserves its true market of purchase with a per-unit origin ledger,
  preventing mixed local/imported lots from falsely earning delivery credit.
- Distinct source-grounded market audits, real factory manufacturing and real
  sale of cross-market imported cargo earn a nonterminal trade checkpoint.
  Retirement requires a subsequent player choice.
- Authored scenes and replay receipts bind source, settings, seed and actions;
  original gameplay is reconstructed rather than trusting client-updated cash.

### Reference scenario

With default settings, this real original action trace should earn a checkpoint:

audit -> manufacture -> harvest -> focus:2 -> buy -> travel:1 -> audit ->
sell -> checkpoint

The tools cargo is produced in the starting market, transported and actually
sold to a different market. The world is still playable after the checkpoint.

### Gates / limitations

New adversarial tests cover cash and stock conservation, impossible movements
and budgets, source scene forgery, mixed-origin cargo, receipt tampering,
nonterminal and voluntary terminal outcomes. The Ubuntu and Windows exact-head
engine workflow checks the new runtime, tests and syntax. Hosted CI completion
must still be observed; adding a workflow is not equivalent to passing one.

Full native Godot gameplay parity, platform binaries, performance device
testing and release/legal review are not claimed.

## Change history — 2026-10-12 (UTC date)

- Original multi-market runtime added (real production, household demand,
  source-bound market prices and distinct original routes).
- Cargo provenance upgraded (per-unit lot custody replaces vulnerable
  last-purchase origin shortcut).
- Editor, scene and replay integrated (the economy now runs through the
  existing game-studio authored session APIs).
- Adversarial regression and cross-OS gates wired (required source replay
  validation; hosted result pending at publication).

## Additional implementation — verified AI planner, CLI and Studio

The same finite market mechanics now feed an original trade director through
advanced_economy_planner.py. The director attempts genuine manufacture, cargo
purchase, adjacent traversal, two district audits and real import sales. No
numeric reward is injected. Inadequate source goods, capital or command budget
return a clearly inconclusive partial plan and cannot be promoted as a win.

CLI adds plan-economy and verify-economy-plan. The token-protected local Studio
adds /api/economy-plan and /api/economy-plan-verify. A human-facing Economy panel
shows the original market state, live inventory/price map, player trade choices,
AI evidence and **explicit human adoption only after independent verification**.
The planner's action receipts are checked again before the local game session
replays them. Source project files are not silently modified.

The exact-head Linux/Windows workflow includes independent planner tests as
well as the runtime, JS syntax and resource-conservation suites.

## Next milestones

1. Exact-head hosted CI and repair of any concrete integration failures.
2. Genuine Godot scene/playback integration and parity, not sidecar-only claims.
3. Independent gameplay and economic UX evaluation under bounded device budgets.
4. Remaining original system families with real mechanics and diverse play.
