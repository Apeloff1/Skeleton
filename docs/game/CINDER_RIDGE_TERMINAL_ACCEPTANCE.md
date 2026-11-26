# Cinder Ridge terminal acceptance

The consumer acceptance command executes a real two-chapter original game twice:

1. Through the canonical campaign engine, with a database close/reopen after
   every committed action and an export verified by deterministic replay.
2. Through the actual numbered terminal interface, quitting at mid-campaign,
   restarting from the persisted SQLite slot and earning both endings.

The interactive action selector verifies that each expected action is actually
offered by the runtime; it never injects a win or bypasses the game rules.

    python -m skeleton.game.gameplay.ridge_rescue consumer acceptance

This is a source-checkout acceptance test, not a claim of Windows laptop
qualification, packaging certification or successful exact-head CI. The
Windows .cmd launcher requires an installed Python 3 interpreter and a
checkout with the skeleton package importable.
