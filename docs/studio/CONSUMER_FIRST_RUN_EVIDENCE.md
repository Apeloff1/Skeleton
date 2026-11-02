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
