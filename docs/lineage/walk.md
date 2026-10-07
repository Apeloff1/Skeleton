# Walk (GB-57)

Parent #80. Additive. Does not call the stage organs.

## Public card

- Steps must be a prefix of admit, quota, place, prefill, decode, check, stock, reclaim.
- A skip fails. The card does not keep the bad steps.
- A spaced name is dropped and not stored.

## Accept

`python -m unittest tests.test_gb57_walk -v`

`python scripts/check_walk.py` exits 0.
