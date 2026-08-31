# Product surface

Operator JSON. No dashboard required.

```
python -m skeleton ready
python -m skeleton product
python -m skeleton health
python -m skeleton next
python -m skeleton seed
python -m skeleton caps
python -m skeleton lattice
python -m skeleton wiki 'SELECT * WHERE kind=principle'
python -m skeleton pulse
python -m skeleton walk -n 3
```

HTTP: `GET /cortex/{product,health,next,ready,caps,lattice,banks,wiki}`  
`POST /cortex/{organismer,galaxy,social,seed,contact,pulse,walk}`

Version stamp lives on the product card (`version`).

## What the organism is

Five Hoag rings (memory, compiler, dream, distiller, editor) around a
wiki nucleus. Mouths sit in the gap and only speak through Jeeves.
Knowledge is house-dialect atoms, T0–T5, stored_prose=0.

## Write path

Stimulus → `skip | update | new` (Jaccard vs wiki). Skip does not mint.
Update/new pulses the five brains. Persist writes merkle ledger +
`state.json` + `galaxy.json` + `vault.ccl` + `journal.jsonl`.

High-value atoms are tagged `internalized` and later near-duplicates
skip. Caps adapt to RAM/CPU/load with 0.62 headroom; shelves trim when
the live cap shrinks.

## Social / field

Pointers only. Catalog + `SOTA_POINTERS` (arXiv / Xarchive / GitHub
labs). `seed` files them into the wiki. Coverage score and wiki topic
count move S, which moves G. No article bodies on the shelf.

Dual-layer cite: https://arxiv.org/abs/2608.22215 — house path is
Jaccard + DreamBrain, not their SFT cascade.

## Persistence

Runtime only. `skeleton/acquired/organism/` and `acquired/galaxy/` are
gitignored. Atom cap is hardware-live, not a fixed 400.

## Laws

cite-do-not-copy · stored_prose=0 · clipped-G · write-route skip|update|new
· headroom-below-wall
