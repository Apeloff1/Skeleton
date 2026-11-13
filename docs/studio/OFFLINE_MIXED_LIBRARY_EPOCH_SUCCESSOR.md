# Independently pinned successor of offline game-library epoch receipts

This command compares **two separate, already published private receipts**.
It is a read-only observational replay proof for a signed/unsigned original-game
library, not a release certificate, signing authority, monotonic counter,
hardware qualification, or replacement for the canonical handoff verifier.

## Acceptance contract

Supply the complete historical sequence (2–5 generations) and the current
sequence (one additional generation, up to six). Each generation contains
bounded JSON arrays of canonical unsigned and signed library entries. Historical
descriptors must match the current prefix exactly, including independent
source, archive, save, signature, key and signer-policy pins. Each current
generation must advance at least one real playable game.

Publish both receipts first with `mixed-library-epoch-handoff` and retain their
SHA-256 pins outside the receipt files. Use:

`python -m skeleton app audit-mixed-library-epoch-successor`

with repeated `--previous-unsigned-generation`,
`--previous-signed-generation`, `--current-unsigned-generation`,
`--current-signed-generation` JSON arguments, two distinct
`--previous-receipt` and `--current-receipt` paths, independently stored
`--previous-receipt-sha256` and `--current-receipt-sha256`, and explicit
`--trusted-local-operator` acknowledgement.

Both receipt inodes must be different and outside all protected original-game
roots. The canonical inspector reopens both receipt files and replays each
complete game and signer-policy history against its independent pin. The
successor must extend the previous chain by exactly one transition with an
identical historical prefix. Full source, save and receipt custody is checked
again after replay to reject swaps, rollback and forks.

## Failure and release handling

Any malformed input, missing operator acknowledgement, reused receipt,
incorrect pin, fork, rolled-back save, modified signer policy, symlink or
untrusted filesystem custody fails closed. The command does not create,
replace, delete or repair files. A successful result does not persist an
anti-rollback counter and cannot detect a malicious operator replacing both
receipts **and** their external pins. Preserve the original receipt pins in
independent trusted custody. No consumer-device, executable-signature,
copyright, or release qualification is implied.
