# Studio A — Reviewed narrative promises and closure proof

This vertical adds an end-user-reachable original-story promise contract. The
author first creates a canonical world using `world-canon`, adds a setup
choice and a distinct payoff choice, then proposes an authored promise. Jeeves
may preview the typed proposal but cannot approve or persist it.

## Authoring and persistence

A promise has an original title, setup, payoff, trigger choice, resolution
choice, and required/optional status. Its `world_digest` leases the exact
canonical world. `world-promises propose` persists an unapproved sidecar.
`world-promises edit` applies strict, atomic add/replace/remove transactions
under an expected digest; every edit revokes approval. Only an operator can
run `approve --note` to record reviewed original content. Browser editing
uses the CSP-hashed `world-promises editor` and `verify-editor` workflow;
the browser exports JSON, never writes source or approves content.

```sh
python -m skeleton world-promises --store PRIVATE propose \
  --world-id harbor --prompt "Keep the vow" --promise-id return_home \
  --title "The return" --setup "The keeper makes a vow" \
  --payoff "The keeper returns" --trigger-choice take_oath \
  --resolve-choice fulfill_oath
python -m skeleton world-promises --store PRIVATE inspect --world-id harbor
python -m skeleton world-promises --store PRIVATE proof --world-id harbor
python -m skeleton world-promises --store PRIVATE approve --world-id harbor \
  --expected-digest SOURCE_DIGEST --note "Reviewed original narrative"
python -m skeleton world-promises --store PRIVATE compile --world-id harbor \
  --expected-digest APPROVED_DIGEST
python -m skeleton world-promises --store PRIVATE verify --world-id harbor
```

## Executable proof and player handoff

A bounded deterministic state search explores every reachable scene, earned
flag set, open promise set and resolved promise set. It rejects any reachable
ending with an unresolved required promise, required promises never triggered,
required promises never resolved, missing endings, and state/step exhaustion.
Optional promises may remain open but are not falsely marked resolved.
Proofs and player views are derived from canonical source and replayed choices,
not mutable client claims. A world source edit invalidates the sidecar lease.

Compilation produces the existing offline interactive HTML5 world player, a
typed promise/closure handoff manifest, and a last-published verification
receipt. The browser world player does not claim to enforce extra promise
rules; the exhaustive source proof is the handoff contract. `verify` reads
every artifact and recompiles from current source, rejecting stale, forged,
partial or tampered publication. It is not device/release certification.

The read-only Jeeves tools `promises.propose_preview`,
`promises.inspect`, `promises.proof`, and `promises.player` expose typed
results without write authority. The operator CLI handles edits, approval,
publication, and verification. The player tool reads the persisted session
and reports triggered, resolved, open and open-required obligations.

## Validation holds

Run `python -m pytest skeleton/testing/test_jeeves_world_promises.py -q`
on the exact source head, then the canonical world and Jeeves regression
suites. No CI or consumer qualification is implied by source publication.
