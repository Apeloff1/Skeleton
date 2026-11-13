# Original-game checkpoint-chain evidence handoff

`python -m skeleton app mixed-library-checkpoint-handoff` publishes a private
no-clobber receipt for an independently pinned, fully replayed series of
historical original-game library handoffs. It accepts 2–5 paired
`--checkpoint` JSON arguments or 2–5 POSIX owner-private
`--checkpoint-file` arguments, never a mixture.

Use `--output /private/new-handoff.json` to publish after complete replay,
then retain the returned `receipt_sha256` in independent operator custody.
Later use `--inspect-receipt /private/new-handoff.json
--expected-receipt-sha256 <externally-pinned-sha256>` with the same checkpoint
descriptors to repeat source, save, signer-policy and receipt replay.

The publisher checks original-game and historical-receipt inode custody before
and after publication, fsyncs the no-clobber private output via the canonical
receipt publisher, and rereads the exact pinned bytes. A post-publication
failure is quarantined for operator inspection, not automatically deleted.

This is point-in-time Python source replay evidence, not native device
qualification, external package signing, persistent rollback protection,
independent signer-policy freshness, content rights, or release approval.
