# Persist 1.0 (GB-27)

Parent #80. One persistence core.

## Gates

- `$SKELETON_OWN` unset → process-local `live_deck` / `live_jeeves`.
- `$SKELETON_OWN` set → `helix.jsonl`, `rotors.json`, `traces/` under that root.

## Not done

- No second persist core.
- No deck.py clobber.

## Accept

`python -m unittest tests.test_gb27_persist -v`

`python scripts/check_persist.py` exits 0.
