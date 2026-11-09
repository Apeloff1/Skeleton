# P3 Trust & Experience

This slice implements the executable behavior owned by
`P3-TRUST-EXPERIENCE-01`.

It binds explanations to exact operation/evidence identities, requires
accessible semantic approval/cancellation/error surfaces, separates
locale-specific presentation from canonical machine parsing, and maintains
time-bounded compliance-control evidence with explicit applicability and owner
identity.

The compliance registry is an evidence/control registry. It intentionally does
not infer legal applicability from geography, product names or user identity.

The canonical module is mirrored exactly through the governed AI tree:

- `skeleton/cognition/trust_experience.py`
- `skeleton/ai/cognition/trust_experience.py`

Run:

    python -m unittest -q skeleton.testing.test_p3_trust_experience
