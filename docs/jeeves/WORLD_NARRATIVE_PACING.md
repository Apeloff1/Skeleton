# Original narrative pacing and climax closure proof

This independent Studio A vertical models authored dramatic pacing across
canonical scene choices. Each scene has an original setup, rising, climax
or resolution phase, bounded intensity and narrative note. The source is
leased to the exact canonical world digest. Every scene must have one
typed beat in sorted ID order. Setup intensity is limited to 0..4,
climax requires 7..10 and resolution is 0..6. A start scene must be setup;
every ending must be resolution. Exhaustive bounded traversal rejects
phase regression and any reachable ending that bypasses the climax.

Author prompt and typed beats produce an unapproved proposal. The operator
CLI `python -m skeleton world-pacing --store DIR` supports propose,
inspect, save, edit, approve, editor, compile, verify, player and
player-slot. Writes are descriptor-anchored, serialized by the world lock
and require exact digest compare-and-swap. Editing always revokes approval.
The offline editor exports only unapproved typed JSON. The HTML5 player
renders scene narrative and pacing notes using textContent, a CSP-hashed
script, no network and no external assets. Receipt verification binds the
world, authored source, exhaustive proof and exact playable bytes.
Jeeves tools expose read-only typed proposal and replay previews.

Focused regression: `python -m pytest skeleton/testing/test_jeeves_world_pacing.py -q`.
No release, device or dramaturgical quality certification is asserted.
