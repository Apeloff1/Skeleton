# Catalog quota (GB-51)

Parent #80. Additive. Does not edit `Harbor`.

## Public card

- Cap 8. Extra tokens drop.
- A spaced item is dropped and not stored.
- `coin=0`.

## Accept

`python -m unittest tests.test_gb51_quota -v`

`python scripts/check_quota.py` exits 0.
