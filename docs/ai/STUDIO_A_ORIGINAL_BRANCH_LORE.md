# Studio A — Original branch-aware lore canon

World lore is authored, not scraped. The author supplies a prompt, subject,
statement and optional additional facts. Every fact binds to an existing
canonical scene and earned choice flags. The validator proves whether the
fact can be revealed on a real route. Mutually contradictory facts are only
permitted on mutually exclusive playable paths.

## User workflow

Use python -m skeleton world-lore --store PRIVATE propose
--world-id marsh --prompt "Write original courier history"
--subject "The letter" --statement "A sealed letter exists".

The returned lore digest is an optimistic edit lease. Use inspect, edit with
strict operation JSON, approve with an explicit original-author review note,
compile using the current digest, and verify the resulting artifacts. Edit
operations add, replace and remove typed facts and can be batched atomically.
Every edit revokes approval. No model is granted automatic write authority.

A saved player can call world-lore reveal --world-id marsh --slot save to
see only facts earned on the actual replayed route, with first-seen steps.
The same world lock serializes source and lore writes. Source changes,
stale CAS, forged player state, noncanonical IDs, unreachable facts,
asymmetric contradictions and proof-budget exhaustion fail closed.

The compile step emits the real canonical offline playable, a no-script
escaped lore atlas, a typed handoff and a source-bound receipt. Verify
independently rebuilds and byte-compares all artifacts.

## Qualification and regression

The graph proof explores (scene, earned flags, revealed facts) states with
a strict cap. Contradictory facts cannot be revealed on the same reachable
trace. The graph proof is not an AI prediction, content-rights license,
native engine certification, device qualification or release acceptance.

Focused tests: python -m pytest
skeleton/testing/test_jeeves_world_lore.py -q

Required exact-head repository security and CI gates remain mandatory.

## Offline browser editing

Use world-lore editor --world-id marsh --expected-digest SHA to publish
an offline CSP-hash-protected HTML editor. Select a fact, revise its subject
or statement, and export a typed replace operation as JSON. Review the
operation and pass it to world-lore edit --operation-json with the exact
source digest. The CLI validates the complete canon graph, revokes approval
and persists only under an optimistic lease. The browser itself has no
filesystem write, network or model authority. Verify the published editor
using world-lore verify-editor --world-id marsh; tampering fails closed.

## Playable integration

Compilation now injects reviewed lore into the canonical offline world player.
Facts are revealed only when the player actually enters their authored scene
with the required earned flags. The browser tracks discoveries across choices
and clears them on restart. No future-branch spoilers are shown. The player
retains the canonical choice and ending transitions, escapes all original
text, uses an exact script hash in its CSP and has no network dependency.
The source-bound receipt and byte-replay verification include this playable.
