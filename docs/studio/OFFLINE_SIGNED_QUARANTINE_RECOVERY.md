# Signed offline quarantine recovery

The application now supports `python -m skeleton app recover-signed-install` for
an existing **damaged original-game source directory**, an independently pinned
ZIP, a detached Ed25519 signature and an independently pinned public key.

The operator must supply `--quarantined`, `--archive`, `--destination`,
`--public-key`, `--signature`, `--expected-archive-sha256`,
`--expected-manifest-sha256`, `--expected-public-key-sha256`, and
`--trusted-local-operator`. The trust pins must be distributed separately
from the untrusted source. The app never loads a private signing key.

Before creating any directory, the operation validates all pins, verifies the
archive signature, inventories the quarantined tree with nofollow descriptor
custody, and preflights a fresh destination. The canonical recovery routine
then atomically reserves a new private directory and installs **only** bytes
from the pinned ZIP. It does not repair or copy the damaged installation.

After installation, an independent archive-to-installed-source comparison
replays the game; the signature, key, archive and quarantine are checked again.
Any mismatch blocks the result. The damaged original remains untouched.
A late failure leaves the fresh destination in place for operator quarantine;
there is no automatic rollback or overwrite.

This is source-level, point-in-time evidence on supported POSIX hosts.
It does **not** certify native package signing, publisher identity, content
rights, Godot execution, consumer hardware, or release readiness. Existing
malware, secret, dependency, workflow-input and exact-head CI holds remain.

For read-only planning, append `--preflight-only`. This validates signature,
quarantine identity and destination availability without reserving or
publishing anything. The preflight is not a lease: the real recovery repeats
all security checks before its atomic no-clobber reservation.
