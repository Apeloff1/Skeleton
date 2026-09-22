# Chronicle helix (GB-28)

Parent #80. Append-only merkle jsonl.

## Public card

- helix.jsonl records observe / forge / gossip roots.
- 3 appends verify.
- Tamper of a middle root fails verify.
- No network. No coin.

## Accept

`python -m unittest tests.test_gb28_helix -v`

`python scripts/check_helix.py` exits 0.
