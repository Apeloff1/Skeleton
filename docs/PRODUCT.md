# Product surface

Canonical operator commands. This page lists only CLI entry points that are dispatched by `skeleton.__main__.main`. The HTTP organism API is separate from the CLI; a route existing does not make a same-named terminal command available.

```sh
# Canonical assembly and runtime inspection
python -m skeleton app status --json
python -m skeleton app check --json
python -m skeleton app status --live
python -m skeleton status
python -m skeleton config
python -m skeleton contracts
python -m skeleton capabilities

# GameForge creator loop
python -m skeleton eras
python -m skeleton generations
python -m skeleton doctor
python -m skeleton walk --era extraction_now -n 3 --mode thermal --json
python -m skeleton walk --all-eras -n 2 --json
python -m skeleton cockpit BIND ERA cozy_wholesome
python -m skeleton run "an original cozy village" --out ./out/village

# Further dispatched surfaces
python -m skeleton app plan --json
python -m skeleton app smoke --json
python -m skeleton help
```

## Legacy organism HTTP API

The `/cortex/*` endpoints remain HTTP interfaces and require their
normal server/security setup. They are **not** synonyms for root-level
`python -m skeleton <verb>` commands.

The older operator command catalog advertised commands that were never
dispatched. Those speculative CLI examples have been removed here rather
than presenting `Unknown command` as a completed product. Reintroduce
individual commands only with working dispatch, proper authorization,
documented failures, and evidence. Track that work in issue #3614.

## Repeated playable walkthrough contract

`walk -n N` and `walk --repeat N` perform 1 to 100 bounded actual
walkthrough attempts. Multi-run invocations use per-attempt deterministic
seeds (`walk:000`, `walk:001`, ... or `<seed>:000`, ...). A single
failure makes the entire command fail. `--all-eras -n N` runs every era
N times; `--json` includes each attempt and the aggregate result. One
walk without `-n` retains its prior output and seed behavior.

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
