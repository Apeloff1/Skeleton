# Viscera 2.5 (GB-22)

Parent #80. Wave 3 adapter. Facade only.

## Artifact not copied

- `artifacts/Viscera/` is not in git.
- torch is not imported.

## Public card

- QK-norm RMS on q/k.
- Specdec accept-until-mismatch.
- Steer h <- h + alpha u-hat.
- Absmax int8 SNR finite.
- Remat second forward == first.
- Every card has `stored_prose=0`.
- `capabilities()` exposes owner, contract, failure_modes, obs, security.

## Accept

`python -m unittest tests.test_gb22_viscera -v`

`python scripts/check_viscera.py` exits 0.
