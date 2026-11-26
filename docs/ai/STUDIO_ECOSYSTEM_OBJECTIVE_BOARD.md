# Offline original-world objective board

The objective board is an editor and playable-handoff **preview** joining
canonical quest state, source-authored scene IDs and original NPC cues.
Completed, available and locked stages are computed from the deterministic
quest replay. Locked objectives display exact missing prerequisites, not
fabricated world events.

## User-facing entry points

    python -m scripts.studio_ecosystem_cli \
      --project studio_arena_fighting_glacial_fjord \
      --objective-board --objective-board-expected-source <source-sha256> \
      --quest-actions '[]' --objective-board-limit 8 \
      --objective-board-html

The JSON receipt includes a script-free accessible HTML preview. The same
operation is exposed as the typed Jeeves tool
\`studio_original_objective_board\`. The optional \`include_html\` flag
requests the same HTML payload. An editor can render it in an offline
sandbox without external network resources; the HTML has a restrictive
Content Security Policy and escapes every authored identifier.

The source digest must match the canonical original blueprint. Continuation
pages require an exact session lease, and each stage/scene card is sourced
from the canonical dialogue compiler. No source files are modified.
Persisted authored edits and compiled playable HTML continue through the
existing revision and compiler workflows.

## Proof and limits

The board is **not** evidence that an NPC spoke, that a native engine ran,
or that a game passed release/device qualification. No external evidence is
minted. Fail-closed guards cover authority, stale leases, invalid replay,
invalid pagination, oversized receipts and HTML injection.

Focused regression:

    pytest -q tests/test_studio_ecosystem_objective_board.py
