# Deterministic offline crafting and finite economy

Canonical owner: skeleton/game/gameplay (FLGB-13).
Installed CLI: skeleton-game-craft (also python -m skeleton.game.gameplay.crafting_cli).

A source-bound authored recipe catalog defines finite owned ingredients, outputs,
currency costs and unlockable recipe prerequisites. Crafting is atomic:
prerequisites and every ingredient are checked before a new immutable state
is returned; an error cannot partially spend or mint inventory. Batch counts,
stacks, recipes, event counts, file bytes and currency are bounded. The
canonical EconomyRule verifies the finite game-currency transfer.

Use inspect/run/verify with --plan, --actions and --save, or play with --plan
and --save. Resume a verified play session using --resume old.json --save
new.json. Saves are deterministic, versioned and bound to the exact source
plan. Restore reconstructs all actions from genesis, compares the complete
state and digest, and rejects tampered or superseded sources. Output is
atomic no-clobber. No network or provider credentials are used.

This is original fictional game currency, not payment processing, digital
asset custody or an economic prediction. Terminal text choice controls do
not claim native rendering, user authorization, device qualification or
a complete released game.

Focused tests: python -m pytest -q skeleton/testing/test_crafting_runtime.py
