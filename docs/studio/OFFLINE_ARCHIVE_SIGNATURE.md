# Detached Ed25519 signature verification for original source ZIPs

This is a **real cryptographic signature verification** over an independently
pinned original browser/Godot source archive. It is not a native executable
package signature or consumer device qualification.

An external trusted signer signs exactly these bytes with Ed25519:

```text
b"Skeleton offline original source archive signature v1\\x00" +
ascii_json({"archive_sha256": "<64-lowercase-hex>",
            "manifest_sha256": "<64-lowercase-hex>",
            "schema": "skeleton.app.offline_source_archive_ed25519.v1"})
```

The JSON is canonical: sorted keys, no spaces, ASCII, with separators
`(",", ":")`. The Python API `source_archive_signature_message`
produces the exact message for an **external** signer. Do not commit private
keys, put them in CLI flags, or derive the public-key trust pin from the
untrusted candidate key.

The detached signature file is 64 raw bytes. The Ed25519 public key file is
32 raw bytes. Both must be owner-controlled regular files without symlink
traversal, and the public-key SHA-256 must be obtained independently.

```sh
python -m skeleton app verify-archive-signature \
  --archive /owner/private/original-source.zip \
  --signature /owner/private/source.sig \
  --public-key /owner/private/trusted.pub \
  --expected-archive-sha256 <independent-archive-pin> \
  --expected-manifest-sha256 <independent-manifest-pin> \
  --expected-public-key-sha256 <independent-key-pin> \
  --trusted-local-operator
```

The verifier independently checks the canonical archive inventory before
and after signature verification, rejects detached-file inode substitution,
and emits a read-only receipt. This proves the bytes were signed by the
holder of the corresponding Ed25519 private key; it does not establish that
the key belongs to a particular publisher. No device was executed and no
rights or release review was performed. Consumer release holds remain.
