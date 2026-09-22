# TurnEngine headless (GB-41)

Parent #80. Play loop without GUI.

## Public card

- Verbs: extract / heat / sleep. improve sleep → dream.
- Warp extracts once.
- 20-tick headless. extract_count == warp_count.

## Accept

`python -m unittest tests.test_gb41_turn -v`

`python scripts/check_turn.py` exits 0.
