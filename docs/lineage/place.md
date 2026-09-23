# Place (GB-52)

Parent #80. Additive. Does not edit `quota` or `TurnEngine`.

## Public card

- One short token. One slot in `0..7`.
- A bool slot, an out-of-range slot, or a spaced token fails.
- A refused token is not stored.

## Accept

`python -m unittest tests.test_gb52_place -v`

`python scripts/check_place.py` exits 0.
