# Offline source trust-policy admission (Studio D)

The new `verify-policy-signed-source` and `install-policy-signed-source`
commands add a **required independent policy pin** to the existing Ed25519
source-archive signature and canonical replay installation. They do not
supersede security, malware, rights, device or consumer release gates.

## Policy custody and scope

A trusted local operator prepares a private, regular, owner-owned
`operator-trust.json` (mode 0600) with exact fields:

```json
{
  "schema": "skeleton.app.offline_source_trust_policy.v1",
  "epoch": 1,
  "archive_sha256": "<independently obtained lowercase sha256>",
  "manifest_sha256": "<independently obtained lowercase sha256>",
  "authorized_key_sha256": ["<sha256 of raw 32-byte Ed25519 public key>"],
  "revoked_key_sha256": []
}
```

The caller must independently pin SHA-256 of **this policy file** as well as
the archive, manifest and raw public key. The policy cannot grant itself
authority. Revocation overrides authorization; a signer present in both
lists is denied. There is no network fetch, key generation or private key
load. Strict JSON decoding rejects duplicate fields, nonfinite values,
unknown fields, excessive sizes and duplicate pins.

The policy is read from an owner-controlled parent through a nofollow file
descriptor. The file must be owner-private, regular, singly linked and
at most 8192 bytes. A second read checks bytes and inode metadata after
signature verification. Symlinks, renamed same-byte files, wrong pins and
changed source scope fail closed.

## Commands

```sh
python -m skeleton app verify-policy-signed-source \
  --archive game.zip --public-key signer.pub --signature game.sig \
  --policy operator-trust.json \
  --expected-archive-sha256 "$ARCHIVE_PIN" \
  --expected-manifest-sha256 "$MANIFEST_PIN" \
  --expected-public-key-sha256 "$KEY_PIN" \
  --expected-policy-sha256 "$POLICY_PIN" \
  --trusted-local-operator

python -m skeleton app install-policy-signed-source \
  --archive game.zip --destination new-game-install \
  --public-key signer.pub --signature game.sig \
  --policy operator-trust.json \
  --expected-archive-sha256 "$ARCHIVE_PIN" \
  --expected-manifest-sha256 "$MANIFEST_PIN" \
  --expected-public-key-sha256 "$KEY_PIN" \
  --expected-policy-sha256 "$POLICY_PIN" \
  --trusted-local-operator
```

The install path verifies the policy before destination reservation, calls
the canonical signed no-clobber installer, replays the installed game and
reverifies the policy afterward. A late failure leaves the destination for
explicit quarantine; it is **not** rolled back, automatically adopted or
marked release-ready.

## Explicit limits

Policy epoch is an observation, **not** monotonic rollback protection.
An operator presenting an old but correctly pinned policy can still admit
an old signer. This is not an online certificate revocation mechanism and
cannot certify legal rights or publisher identity. Source signature is not
a signed executable package. Device and consumer release qualification
remain blocked until independent checks are completed.

Focused acceptance:
`python -m pytest skeleton/testing/test_app_offline_source_trust_policy.py -q`.
These tests must be run against the final SHA before promoting or merging.
