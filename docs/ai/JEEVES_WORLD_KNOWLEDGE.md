# Reviewed NPC knowledge and disclosure proof

The Studio A world-knowledge vertical connects an original author prompt to a
typed fact/reveal proposal, source-leased edits, explicit review, exhaustive
reachable-state disclosure checks, a CSP-restricted offline HTML5 player, and
byte-for-byte verified artifact receipts. It does not use a model to invent
facts, authenticate a narrator, or guarantee confidentiality of embedded facts.

## Prerequisites and authoring

First publish a canonical world with world-canon and an approved original cast
with world-cast in the same private store. The knowledge source is leased to the
exact SHA-256 digest of both. Example:

    python -m skeleton world-knowledge --store ./private-worlds propose \
      --world-id archive --prompt "An original observatory secret" \
      --fact-id constellation --title "Seven new stars" \
      --detail "The fictional map reveals seven original stars." \
      --choice pursue_goal --speaker narrator --recipient player

This creates a review-required private JSON source. A narrator disclosure
means the author intentionally reveals the fact after a canonical choice.
Actor disclosures instead require the actor to have earned the fact on every
reachable source-state where that choice is enabled, and to be physically present
in the source scene. No unearned actor disclosure is silently repaired.

Inspect the source and its SHA-256 lease:

    python -m skeleton world-knowledge --store ./private-worlds inspect \
      --world-id archive
    python -m skeleton world-knowledge --store ./private-worlds proof \
      --world-id archive

Use edit --operation-file operation.json --expected-digest DIGEST for atomic
typed add/replace/remove operations on facts, disclosures, and dialogue claims.
Edits revoke approval and reject dangling references. The operation file must
be a bounded regular file, not a symlink or FIFO. A claim is a pair of line and
fact IDs; claims are checked for every reachable scene/flag/knowledge state
where the line is spoken. Unannotated dialogue is not semantically understood.

After review:

    python -m skeleton world-knowledge --store ./private-worlds approve \
      --world-id archive --expected-digest DIGEST --note "Reviewed original fact"
    python -m skeleton world-knowledge --store ./private-worlds compile \
      --world-id archive --expected-digest NEW_DIGEST
    python -m skeleton world-knowledge --store ./private-worlds verify \
      --world-id archive

The compilation writes archive.knowledge.playable.html,
archive.knowledge.handoff.json, and archive.knowledge.receipt.json.
Verification recomputes exact bytes from the leased world, cast, and knowledge
source; it fails on stale digests, altered artifacts, or missing files. A
source-bound player replay may be obtained with player --slot SLOT after
creating a canonical world-session. A model can only use the read-only typed
Jeeves tools knowledge.propose_preview, knowledge.inspect, knowledge.proof, and
knowledge.player; it cannot publish or approve.

## Security and scope

All custody writes use the existing descriptor-anchored WorldStore and its
per-world exclusive optimistic lease. The graph proof is bounded to 2,048
reachable knowledge states and 512 replay steps; exhaustion is an error, not a
pass. Player knowledge is derived from independently replayed canonical choices,
not from untrusted saved fact lists. The HTML player has a no-network CSP and
uses textContent, never HTML injection. Facts remain visible to anyone who
inspects the HTML source; do not embed secrets or unreleased licensed material.
Digest receipts establish integrity against accidental changes, not identity
authentication or independent release certification. No consumer, hardware,
privacy, accessibility, or device qualification is implied.

Focused tests:

    python -m pytest -q skeleton/testing/test_jeeves_world_knowledge.py
