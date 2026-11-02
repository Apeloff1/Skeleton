# Consumer first-run release evidence boundary

Run the canonical app command after an original game has been exported,
installed, played, saved and restored. The command reexecutes the real
source-level acceptance adapters and returns a deterministic SHA-256 of
their in-memory evidence. It **never** signs or publishes a release.

Single game:

```sh
python -m skeleton app consumer-release-evidence --mode single \
  --installed "$INSTALL" --archive "$ZIP" --save "$SAVE" --receipt "$RECEIPT" \
  --expected-manifest-sha256 "$MANIFEST_PIN" \
  --expected-archive-sha256 "$ARCHIVE_PIN" \
  --expected-save-sha256 "$SAVE_PIN" \
  --expected-receipt-sha256 "$RECEIPT_PIN" --trusted-local-operator
```

Cohort (2–8 independently pinned installed games):

```sh
python -m skeleton app consumer-release-evidence --mode cohort \
  --jobs-file "$PRIVATE_JOBFILE" --expected-jobs-sha256 "$JOB_PIN" \
  --summary "$SUMMARY" --expected-summary-sha256 "$SUMMARY_PIN" \
  --trusted-local-operator
```

The independent pins must be retained outside the package being inspected.
Cohort mode can additionally use `--verify-original-sources` to replay
original authoring sources. The private jobfile must remain owner-controlled.
Wrong pins, missing authorization, mixed-mode inputs and forged release
claims fail closed. The digest is an unkeyed checksum of the *observed*
in-memory evidence, not an independent attestation or a signature.

A successful source-level replay is **not** a successful consumer release.
Device, native Godot, installer lifecycle, guarded local AI, signing,
content-rights, persistent nested asset custody and exact-head security/CI
qualification remain blocked until independently verified. No model secrets,
package signatures or device claims are synthesized by this command.
