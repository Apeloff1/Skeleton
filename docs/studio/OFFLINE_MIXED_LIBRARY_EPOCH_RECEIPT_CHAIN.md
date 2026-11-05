# Offline original-game epoch receipt chain

A user may publish a new owner-private handoff after each real gameplay
generation. A single handoff proves only one observed history. The
`audit-mixed-library-epoch-receipts` CLI verifies an entire series of
**2–5 independently pinned handoffs**, each extending the previous by exactly
one generation (from two through six generations total).

Each `--checkpoint` is bounded JSON containing four exact keys:
`unsigned_generations` (list of unsigned game-entry arrays),
`signed_generations` (list of signed game-entry arrays), `receipt` (path
to a previously published private receipt), and `sha256` (independent
lowercase SHA-256 pin for that receipt). Repeat the argument in chronological
order, then supply `--trusted-local-operator`.

The verifier rejects duplicate receipt names, hardlink aliases, repeated pins,
missing generations, historical forks, replay rollback, changed game archives,
signer-policy substitutions and modified private saves. Each adjacent pair
reexecutes both complete game histories against its independently pinned
receipt bytes, and all source/receipt identities are checked again afterward.

This command is read-only and never creates, repairs, signs or publishes a
receipt. It does **not** implement a durable monotonic clock or authenticated
external ledger. If an attacker controls the independently stored pins as well
as the receipts, the result is not persistent anti-rollback proof. Preserve
all security, rights, device, executable-signing and release holds.
