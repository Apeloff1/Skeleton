# Delivery custody v2

New delivery packages are one-document encrypted records with an owner scope,
hashed capability credential, full content digest, expiry and atomic quota.
There is no shared Boardroom filename-based byte registry or memory-only
fallback. Authenticated owner access and explicit bearer redemption are distinct.
The Studio verifies exact SHA-256 before saving/sharing bytes; credentials can
be rotated and copied explicitly and are not appended to new URLs.

Configure JEEVES_DELIVERY_KEY as an independent Fernet key in production.
Absent configuration, the key is atomically generated in Mongo metadata:
this protects against accidental plaintext reads, not database compromise.
Legacy unowned records are retained and require an operator-reviewed migration.
The current 8 MiB cap fits Mongo document limits; larger artifacts require a
qualified chunked store. Concurrent same-project checkpoint admission is scoped
and fenced by run ID; full exactly-once package publication remains outstanding.

Focused:
    cd backend && python -m pytest -q tests/test_chronological_delivery_scope.py tests/test_chronological_workflow_checkpoint.py
    cd frontend && node --experimental-strip-types --test scripts/test-jeeves-delivery-custody.mjs
    cd frontend && yarn typecheck
