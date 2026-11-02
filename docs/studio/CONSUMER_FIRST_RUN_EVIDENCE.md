# Consumer first-run evidence — source-level only

`python -m skeleton app consumer-first-run-readiness` accepts an existing
installed original game, its ZIP, private replay save and private delivery
receipt. The operator must supply four independently retained lowercase
SHA-256 pins and `--trusted-local-operator`. The command runs the canonical
installed-game/replay/receipt assurance **twice**, with descriptor-backed
inode custody snapshots before, between and after both passes.

This command never installs, signs, repairs, rolls back, overwrites, starts
services, invokes Jeeves, or executes a native Godot binary. A successful
exit proves only the observed source-level Python replay at that instant.
The returned `runtime_observation` is descriptive, **not** a verified device.

Release holds remain active for actual Windows/WSL2/consumer laptop install
and recovery testing, native Godot runtime execution, authenticated guarded
local-AI to Jeeves to builder qualification, signer custody, rights review,
malware/secret/CodeQL/workflow-input gates, and final-head CI. Do not treat
this diagnostic as a package signature or release certificate.

## Example

```sh
python -m skeleton app consumer-first-run-readiness \
  --installed /private/games/installed \
  --archive /private/games/game.zip \
  --save /private/games/save.json \
  --receipt /private/games/receipt.json \
  --expected-manifest-sha256 "$MANIFEST_PIN" \
  --expected-archive-sha256 "$ARCHIVE_PIN" \
  --expected-save-sha256 "$SAVE_PIN" \
  --expected-receipt-sha256 "$RECEIPT_PIN" \
  --trusted-local-operator
```

Store pins independently of the untrusted game files. Never commit pins for
private game receipts, user paths, secrets, or personal device identifiers.

## Pinned 2–8 game consumer cohort

`python -m skeleton app consumer-first-run-cohort` is the read-only
multi-game integration path. First publish a canonical cohort with
`first-playable-jobfile --mode publish`; keep its summary SHA-256 outside
the installed game tree. Prepare a separate owner-private, mode-0600 job
file containing all independently pinned game archive, save and receipt
digests, then retain the SHA-256 of that job file separately as well.
Do not copy an untrusted output's self-reported digest into the trusted
command arguments without operator-side verification.

```sh
python -m skeleton app consumer-first-run-cohort \
  --jobs-file /private/cohort/pinned-jobs.json \
  --expected-jobs-sha256 "$JOBS_PIN" \
  --summary /private/cohort/summary.json \
  --expected-summary-sha256 "$SUMMARY_PIN" \
  --trusted-local-operator
```

This checks the original canonical cohort twice and separately reexecutes
each installed game, private save, ZIP and receipt twice, with full-cohort
inode custody fences between games. Every replay must match the original
cohort's project ID, world digest, replay digest, action count and four
independent game pins. A substituted receipt inode is rejected even if
its bytes are identical. The private job-file inode and contents are
revalidated after the operation, including on error. No game, save or
receipt is published, repaired or deleted by this inspection.

Add `--verify-original-sources` only when the original authoring trees
remain available and the operator wants source provenance replay as well.
Without this option, a previously delivered game remains inspectable after
its original authoring tree has been intentionally retired. The option
does not establish original-content rights, a trusted signature, or a
verified hardware device.

A successful JSON result always contains `release_certified: false`,
`native_device_qualified: false`, `package_signed: false` and the
explicit release holds. If any required pin, path custody, replay,
summary, or source check fails, the CLI exits nonzero with a blocked
receipt and does not attempt recovery. Preserve failed artifacts for
explicit operator quarantine and investigation.

