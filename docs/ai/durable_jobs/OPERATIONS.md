# Operations and recovery playbook

Operate only after verifying the external model license, pinned exact model
and tokenizer hashes, 0700 state root, 0600 SQLite stores, no hostile symlinks
and a supported local system. A failed privacy, capacity or integrity check
blocks new work; do not bypass it by enabling a hosted provider.

1. Admit immutable source-bound jobs, fixed request IDs and expiration.
2. Read authenticated owner, resource pressure and queue capacity.
3. Claim per-tenant work using a random lease token and bounded window.
4. Invoke existing OfflineAIService.turn with the original session, request
   identity and text. Never re-derive the request from model-authored plans.
5. Commit the exact native reply receipt to the existing chat store; mirror
   the text digest and model identity into the work queue as a separate record.
6. On success verify the committed work result and integrity event chain.
7. On uncertain generation, worker loss, expiry or ambiguous acknowledgement,
   hold the work rather than automatically regenerating.
8. Reconcile only with explicit operator approval AND an independently
   trustworthy check of authoritative chat absence or committed receipt.
9. Do not merge, promote or release without exact-head CI and device evidence.

Owned operations remain read-only except for explicit queue transitions.
Remote network calls, shell execution, generated-code evaluation, arbitrary
filesystem writes and model-generated operator credentials remain forbidden.
