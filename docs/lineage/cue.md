# Cue (GB-46)

Parent #80. Five axes. Tokens only. Stimulus dropped.

## Public card

- Axes: house, topic, depth, think, obscure. One tick, one axis.
- Closed vocab. No sentence in the card.
- Card `{kind:cue,i,last,axis,tokens,dropped,stored_prose:0}`.

## Accept

Five ticks cover each axis once. Tokens are `xarchive plan r1 why yarn`.

A stimulus string does not appear on the card. `dropped=1`.

`python -m unittest tests.test_gb46_cue -v`

`python scripts/check_cue.py` exits 0.
