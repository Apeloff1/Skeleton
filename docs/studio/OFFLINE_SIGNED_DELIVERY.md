# Signed original-game delivery acceptance

This read-only operator command binds **four independent trust inputs**:
canonical original source ZIP SHA-256, its release-manifest SHA-256,
owner-private replay-save SHA-256, and a separately trusted Ed25519 public
key SHA-256. The detached signature is verified twice across the complete
installed-game/archive/save replay assurance, with inode fences on all inputs.

```sh
python -m skeleton app signed-delivery-assurance \
  --installed /owner/private/installed-game \
  --archive /owner/private/original-source.zip \
  --save /owner/private/progress.json \
  --public-key /owner/private/source-key.pub \
  --signature /owner/private/source.sig \
  --expected-archive-sha256 <independent-archive-pin> \
  --expected-manifest-sha256 <independent-manifest-pin> \
  --expected-save-sha256 <independent-save-pin> \
  --expected-public-key-sha256 <independent-key-pin> \
  --trusted-local-operator
```

A success receipt proves point-in-time source archive signature verification,
installed-source byte equality to the pinned ZIP, Python canonical gameplay
reexecution, and the private save's world/replay binding. It does **not**
prove publisher identity, original-content rights, native executable package
signing, Godot hardware execution, device certification or consumer release.
Those gates remain explicit release holds. No private signing key is used.
