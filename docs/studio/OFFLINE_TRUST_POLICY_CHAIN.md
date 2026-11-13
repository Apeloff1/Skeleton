# Offline trust-policy chain inspection

`python -m skeleton app inspect-trust-policy-chain` inspects 2–16 ordered,
independently pinned local signer-policy JSON snapshots without publishing,
modifying, or authorizing any installation. Each policy must be an owner-private
regular file in an owner-controlled directory; symlinks and hardlinks fail closed.

Pass `--policy PATH --expected-policy-sha256 HEX` once per snapshot in
chronological order, followed by independently obtained
`--expected-archive-sha256 HEX`, `--expected-manifest-sha256 HEX`, and
`--trusted-local-operator`. Do not obtain the independent pins from the
untrusted files being inspected. All snapshots must scope the same original
archive and manifest. Each adjacent pair must increase the epoch, preserve
explicit revocations, and make a substantive signer change. A later snapshot
cannot resurrect a previously revoked key. At least one active signer is
required in every snapshot.

The inspector re-reads all policy inodes after pairwise verification, rejecting
replacements and changed bytes, and emits machine-readable transition receipts.
No private signing key is read. This is **not** a monotonic durable anti-rollback
register, a proof that the supplied last policy is current, a publisher identity
certificate, a copyright license, a signed executable package, or a verified
consumer-device result. All consumer release and security gates remain held.
