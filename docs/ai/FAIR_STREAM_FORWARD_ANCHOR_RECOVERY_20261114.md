# Explicit recovery: external high-watermark CAS gap

This seam repairs exactly one case: the canonical SQLite state committed,
but the independent anchor remains one generation behind. Stop all existing
dispatch owners and establish exclusive operational custody. Inspect the
candidate with `inspect_forward_candidate`; review the successor and its
lineage using trusted operator procedures. The independent operator signs the
exact descriptor using Ed25519 and a fresh nonce. Pin the public key from
trusted configuration, not from the recovery request. Invoke
`recover_forward_anchor` using the already securely opened store.

The repair checks the signed candidate again while preventing SQLite writers.
It advances the anchor with CAS, verifies the new anchor and returns a newly
verified session. It does not change the SQLite payload, reconstruct prompts,
retire a pending lease, execute inference, or treat recovery as a result
receipt. A remaining pending lease still requires separate execution recovery.

A missing anchor, database rollback, multi-generation gap, bad MAC, stale
approval, lineage mismatch or interrupted CAS must not authorize a retry.
If the CAS committed before its response was lost, normal verified reopening
can confirm the matching pair; do not reset or roll back the anchor. The seam
does not provision a production independent anchor, prove physical durability,
or implement a public recovery endpoint. Simulated regression fixtures are not
hardware qualification.
