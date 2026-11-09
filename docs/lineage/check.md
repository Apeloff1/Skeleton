# Stamp check (GB-50)

Parent #80. Additive. Does not edit `TurnEngine` or `delta`.

## Public card

- `stamp=0` and `rebuild=0` passes. `ok=1`.
- A stamp or a rebuild fails. `ok=0`.
- Other fields are not kept.

## Accept

`python -m unittest tests.test_gb50_check -v`

`python scripts/check_stamp.py` exits 0.
