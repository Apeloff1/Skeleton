# Stock (GB-53)

Parent #80. Additive. Does not edit `place` or `check`.

## Public card

- One token per slot. Cap 8.
- A second token on the same slot is a collision.
- A spaced token is dropped and not stored.
- The card keeps slot ids, not the token text.

## Accept

`python -m unittest tests.test_gb53_stock -v`

`python scripts/check_stock.py` exits 0.
