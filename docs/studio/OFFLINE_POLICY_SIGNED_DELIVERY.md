# Read-only policy-signed delivery assurance

`python -m skeleton app policy-signed-delivery-assurance` verifies an
installed original game against its independently pinned ZIP, detached
Ed25519 signature, owner-private replay save and operator-pinned trust policy.
It checks key revocation and source scope before and after canonical delivery
assurance, fences same-byte policy inode substitution, and requires real
offline gameplay replay.

Required inputs: `--installed`, `--archive`, `--save`, `--public-key`,
`--signature`, `--policy`, the five `--expected-*-sha256` pins for
archive, manifest, save, public key and policy, plus
`--trusted-local-operator`.

This is strictly read-only and does not approve content rights, establish
publisher identity, certify a native executable package, establish current
policy freshness or qualify a consumer device. An independently supplied
old policy hash can still admit an old key; key epoch is descriptive only.

End-to-end acceptance:
`python -m pytest skeleton/testing/test_app_offline_policy_signed_delivery.py -q`.
The test suite must run on the exact final SHA and required security/CI gates
must pass before release.
