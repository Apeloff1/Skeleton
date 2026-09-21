# Hive 1.0 (GB-25)

Parent #80. Wave 3 adapter. Facade only.

## Not present

- No chain.
- No coin.
- No network gossip transport.

## Public card

- mint / link / card{root} on forge.
- Two gossip calls produce history length >= 2 and a merkle consensus.
- Walk path cap 8.
- tick increments then gossips.
- Every card has `stored_prose=0`.

## Accept

`python -m unittest tests.test_gb25_hive -v`

`python scripts/check_hive.py` exits 0.
