# Prefill (GB-54)

Parent #80. Additive. Does not edit `place` or `stock`.

## Public card

- Occupied slots stay. Empty slots in `0..7` are the fill.
- The fill token must be short. A spaced fill fails and is not stored.
- Bad occupied entries drop. They are not kept.

## Accept

`python -m unittest tests.test_gb54_prefill -v`

`python scripts/check_prefill.py` exits 0.
