# Decode (GB-55)

Parent #80. Additive. Does not edit `TurnEngine` or looped kernels.

## Public card

- `r1` and `r2` pass.
- `r3halt` passes only when `halt=1`.
- A bool halt or a spaced depth fails and is not stored.

## Accept

`python -m unittest tests.test_gb55_decode -v`

`python scripts/check_decode.py` exits 0.
