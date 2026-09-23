# Playable delta (GB-44)

Parent #80. Additive. Does not edit `TurnEngine`.

## Public card

- Moved counts are a delta. `stamp=0`. `rebuild=0`.
- Identical cards are a stamp. `stamp=1`. Still `rebuild=0`.

## Accept

`python -m unittest tests.test_gb44_delta -v`

`python scripts/check_delta.py` exits 0.
