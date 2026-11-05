# Offline delivery cross-custody assurance (Studio D)

This command binds three **independently pinned** artifacts to one original
playable game: an already installed browser/Godot source tree, the canonical
offline source ZIP used for installation, and an owner-private replay save.

```sh
python -m skeleton app delivery-assurance \
  --installed /owner/private/installed-game \
  --archive /owner/private/original-source.zip \
  --save /owner/private/progress.json \
  --expected-manifest-sha256 <64-lowercase-hex> \
  --expected-archive-sha256 <64-lowercase-hex> \
  --expected-save-sha256 <64-lowercase-hex> \
  --trusted-local-operator
```

The three pins must come from a separately trusted channel. Never derive a
trust pin from the candidate artifact during verification. The explicit local
operator flag is an acknowledgement, not authentication or a privilege bypass.

The gate runs the canonical source-vs-archive inventory and winning-path
replay, replays the private save against the independently pinned archived
world, and reconciles the saved actions against the installed world. It then
rechecks all three custody planes and refuses inode substitution, mismatched
world IDs/digests, replay mismatch, untrusted paths and incomplete proofs.

All checks are **read-only**. This is point-in-time evidence, not a durable
filesystem lock, installer transaction, migration rollback, rights review,
model quality assessment, hardware execution, signed-package attestation, or
consumer-release qualification. The receipt always carries explicit
`native_device_qualified=false`, `rights_certified=false`,
`package_signed=false`, and `release_certified=false` fields.

A failed check returns exit code 2 with a bounded JSON failure receipt on
stderr. No success receipt is published. Existing files are never modified,
deleted or silently quarantined by this command. Do not promote or release
until required exact-head security, CI, signed-package and device gates pass.
