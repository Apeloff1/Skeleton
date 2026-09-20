# Motive 1.0 (GB-21)

Parent #80. Wave 3 adapter. Facade only.

## Artifact not copied

- `artifacts/Motive/` is not in git.
- `skeleton.spine` is not imported. Spine bus is thin.

## Public card

- Unit object S.
- Sigma (suspend), Omega (loop), smash.
- Omega Sigma ≃ id on S.
- Map(S,S) = S (generator count).
- heart(S) = H0 = 1.
- Every card has `stored_prose=0`.
- `capabilities()` exposes owner, contract, failure_modes, obs, security.

## Accept

`python -m unittest tests.test_gb21_motive -v`

`python scripts/check_motive.py` exits 0.
