# Reclaim (GB-56)

Parent #80. Additive. Does not edit `stock`.

## Public card

- A held slot in `0..7` can be freed.
- An unheld ask is a miss. It is not freed.
- A repeat is a collision. A spaced ask is dropped and not stored.
- The card keeps slot ids, not token text.

## Accept

`python -m unittest tests.test_gb56_reclaim -v`

`python scripts/check_reclaim.py` exits 0.
