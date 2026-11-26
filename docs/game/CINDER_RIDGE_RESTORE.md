# Cinder Ridge portable save restoration and consumer acceptance

A portable JSON export can now be restored to a **new** save slot with full
canonical action history. This is a real game restoration, not a copy of a
claimed status: the bundled original campaign is replayed turn by turn, all
CAS heads are recomputed, and SQLite stores the restored session and its audit
ledger in one transaction. Existing slots are never overwritten.

On Linux/macOS, from a source checkout:

    python -m skeleton.game.gameplay.ridge_rescue consumer export --slot adventure
    python -m skeleton.game.gameplay.ridge_rescue consumer restore --slot recovered --file /path/to/export.json
    python -m skeleton.game.gameplay.ridge_rescue consumer audit --slot recovered
    python -m skeleton.game.gameplay.ridge_rescue consumer play --slot recovered

On Windows, arbitrary external file paths are not accepted by the consumer
import path because the portable Python runtime cannot guarantee descriptor-
anchored handling of reparse-point races. Pipe UTF-8 export bytes instead:

    Get-Content -Raw -Encoding UTF8 .\export.json | py -3 .\cinder-ridge.pyz restore --slot recovered --file -
    py -3 .\cinder-ridge.pyz audit --slot recovered
    py -3 .\cinder-ridge.pyz play --slot recovered --ascii

The same `--file -` input is supported for `verify-export` on all hosts.
Input is bounded to 1,000,000 bytes, and an interactive stdin without a pipe
is rejected. Invalid, foreign, tampered, over-budget or incomplete exports
cannot create a save slot. Retry-bearing exports are intentionally rejected
until a future versioned format carries the full retry chronology. This
restriction preserves audit integrity rather than inventing missing turns.

The cross-process source and standalone zipapp smoke tests now exercise
play, quit, restart, both earned endings, export, restore to a fresh slot,
full action-history audit, duplicate restore rejection and corrupted import
rejection. Run the existing Windows smoke launcher on a real Windows laptop;
neither authored tests nor Linux execution certify Windows or release.
