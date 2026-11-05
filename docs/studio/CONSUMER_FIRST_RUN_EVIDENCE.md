# Consumer first-run evidence — source-level only

`python -m skeleton app consumer-first-run-readiness` accepts an existing
installed original game, its ZIP, private replay save and private delivery
receipt. The operator must supply four independently retained lowercase
SHA-256 pins and `--trusted-local-operator`. The command runs the canonical
installed-game/replay/receipt assurance **twice**, with descriptor-backed
inode custody snapshots before, between and after both passes. This
tracks the installed root, evidence-file inodes, and a bounded descriptor-
anchored inventory of every nested package inode at replay boundaries.
Equal snapshots detect same-byte inode substitutions between observations,
but do **not** create a filesystem lock or persistent rollback protection.
Canonical ZIP/installed-content verification remains independently required.

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

## Cross-game nested inode custody

The cohort inspector also takes a bounded, descriptor-anchored snapshot of
**every installed game** before the first canonical replay, after that replay,
after each individual game's two-pass replay, and after the final canonical
cohort replay. A late same-byte replacement of an earlier game's nested
asset is rejected even if its root inode and independently pinned hashes
still match. Every consumer game's reported snapshot digest must equal the
corresponding cohort baseline; a merely well-formed digest is insufficient.
The JSON field `all_games_nested_inodes_checked_after_each_replay` records
these observational checkpoints. This does not lock the filesystem, prove
continuous custody between snapshots, or qualify a native consumer device.

Focused acceptance: `python -m pytest -q
skeleton/testing/test_app_consumer_first_run_cohort.py`. Adversarial
coverage includes first-pass, late cross-game, final-pass same-byte inode
substitution, and forged well-formed nested inventory digests.

With `--verify-original-sources`, the same bounded cohort-wide inode
barriers also cover each original authoring source tree, including nested
assets. A late same-byte substitution of an earlier game's original source
cannot be accepted merely because canonical content digests still match.
Without this option no original source directory is required or scanned.
These checks are observational, not proof of rights or continuous custody.

## Evidence parent-directory continuity

The single-game readiness reader captures both the evidence-file inode and
its owner-controlled **parent directory inode** for the installed root,
ZIP, private save, and receipt. Replacing a parent directory while moving
the same underlying file inode into the new directory is rejected at the
next replay boundary, even when the file digest remains identical. This
closes a path-custody gap not addressed by file-only inode comparisons.
No persistent lock or device qualification is implied.

Cohort acceptance also snapshots the parent-directory identities of every
game's installed root, archive, private save, and receipt before replay,
and rechecks all of them at each cross-game barrier. A later game cannot
launder a replacement evidence parent for an earlier game merely by moving
the original file inode into the new directory.

The cohort summary's parent directory is independently fenced as well:
moving an unchanged summary file inode into a replacement parent is
rejected after any later game replay. The receipt remains observational;
all device, signing, rights and release holds stay in force.
