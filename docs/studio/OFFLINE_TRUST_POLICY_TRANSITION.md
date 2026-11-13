# Read-only source signer rotation and revocation transition

`python -m skeleton app inspect-trust-policy-transition` compares two
independently pinned owner-private trust policy files for the same original
archive and manifest. It requires `--current-policy`,
`--proposed-policy`, `--expected-current-policy-sha256`,
`--expected-proposed-policy-sha256`, `--expected-archive-sha256`,
`--expected-manifest-sha256` and `--trusted-local-operator`.

Admission requires a strictly increasing epoch, no removal of explicit
revocations, no authorized/revoked overlap in the proposed policy, at least
one active proposed signer, and a real key authorization/revocation change.
Both policy files are read with nofollow, owner-private, bounded descriptor
custody and checked again for byte and inode replacement. No files are
created or modified.

**Scope limitation:** This proves only consistency between the two supplied
policy snapshots. The operator must independently establish that the
proposed SHA-256 is the correct current policy. There is no persistent
monotonic epoch store, online revocation authority or automatic publication.
It does not qualify native devices, package signatures, publisher identity,
rights or consumer release.

Focused acceptance:
`python -m pytest skeleton/testing/test_app_offline_trust_policy_transition.py -q`.
