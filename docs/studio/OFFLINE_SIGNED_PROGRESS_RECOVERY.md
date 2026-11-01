# Signed quarantine recovery with preserved progress

`python -m skeleton app recover-signed-progress` rebuilds a damaged original
game **without reading executable source from the damaged directory**. It
requires an independently pinned ZIP, detached Ed25519 signature, pinned
public key and independently pinned owner-private replay save.

Required flags: `--quarantined`, `--archive`, `--destination`,
`--original-save`, `--migrated-save`, `--public-key`, `--signature`,
`--expected-archive-sha256`, `--expected-manifest-sha256`,
`--expected-save-sha256`, `--expected-public-key-sha256`, and
`--trusted-local-operator`.

The operation inventories the damaged directory read-only, verifies signature
and save compatibility before publication, installs a new source tree using
atomic no-clobber directory reservation, and publishes the migrated private
save with independent no-clobber custody. It then verifies the signed archive,
installed source and replay again, and checks that the damaged source and all
original trust inputs retain their identities.

A late failure leaves the newly created game and/or save for explicit
quarantine; it does not delete either destination or mutate the damaged
original. Installation and save publication are **not one transaction**.
All release, native package signing, publisher identity, rights, hardware and
device-qualification holds remain active.

A read-only `--preflight-only` mode checks the signed archive, original
private save replay, quarantined tree and both new destination paths without
publishing either output. Preflight is observational, never a reservation;
the recovery operation repeats all admission checks before publication.
