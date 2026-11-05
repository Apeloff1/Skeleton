# Signed original source install — pre-reservation cryptographic gate

Use this command to install an original game ZIP only after verifying its
detached Ed25519 signature and three independent pins: source archive digest,
release-manifest digest, and trusted public-key digest.

```sh
python -m skeleton app install-signed-source \
  --archive /owner/private/original-source.zip \
  --destination /owner/private/new-game \
  --public-key /owner/private/trusted.pub \
  --signature /owner/private/original-source.sig \
  --expected-archive-sha256 <independent-archive-pin> \
  --expected-manifest-sha256 <independent-manifest-pin> \
  --expected-public-key-sha256 <independent-key-pin> \
  --trusted-local-operator
```

The source signature is checked **before** any destination is reserved. The
canonical installer independently validates and atomically reserves a fresh
directory, installs the pinned source and reexecutes the canonical Python
gameplay. The command then reconciles every installed byte to the ZIP and
verifies the detached signature again. All source/key/signature inode identities
must remain stable across the operation.

The destination is never overwritten. A late failure leaves the newly created
directory for explicit quarantine; there is no destructive automatic rollback.
This does not sign or certify a native executable package, establish publisher
identity, verify original-content rights, execute Godot on a real device, or
qualify consumer release. Existing security and device holds remain active.
