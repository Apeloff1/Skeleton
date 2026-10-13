# Product surface

Operator JSON. No dashboard required.

```
python -m skeleton ready --fix --walk -n 2
python -m skeleton product
python -m skeleton health
python -m skeleton doctor
python -m skeleton next
python -m skeleton wiki 'SELECT * WHERE kind=principle' --limit 24
python -m skeleton seed
python -m skeleton caps
python -m skeleton lattice
python -m skeleton pulse
python -m skeleton orch
python -m skeleton season -n 2
python -m skeleton scoreboard
python -m skeleton hot
python -m skeleton coverage
python -m skeleton decade
python -m skeleton bank --reset
python -m skeleton switch mobile
python -m skeleton witness
python -m skeleton gov
python -m skeleton cage
python -m skeleton rot
python -m skeleton fieldcov
python -m skeleton enact
python -m skeleton day -n 2
python -m skeleton week --days 2
python -m skeleton calendar
python -m skeleton conductor
python -m skeleton conductor --run
python -m skeleton conductor --commit
python -m skeleton ctx "plan tensor ttk"
python -m skeleton ctx "plan tensor ttk" --replay
python -m skeleton ctx "plan tensor ttk" --refine
python -m skeleton live "plan tensor ttk"
python -m skeleton observe
python -m skeleton stacks
python -m skeleton mix
python -m skeleton satellites
python -m skeleton path
python -m skeleton bound
python -m skeleton fieldwalk -n 2
python -m skeleton dump --hot
python -m skeleton orgwalk -n 3
python -m skeleton sleep --force
python -m skeleton forget "old trace"
python -m skeleton helix
python -m skeleton recall mem0
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

## Verified CLI routing batch (13 October 2026)

Four advertised operator entrypoints now actually dispatch to their existing
canonical owners, without synthetic success payloads:

| CLI | Existing owner |
| --- | --- |
| `ready --fix --walk -n 2` | `skeleton.organism.ready.ready_card` |
| `product` | `skeleton.organism.product.product_card` |
| `health` | `skeleton.organism.health.health_card` |
| `next` | `skeleton.organism.next.hint` |

All render source-backed JSON cards. Health/ready return exit 1 when the
underlying card reports `ok=0`; invalid flags or out-of-budget ready walks
return 2. Other documented product verbs remain to be audited and dispatched;
**do not interpret this batch as closing all #3614 verb parity**.

## Operator verb contract — October 2026

Every command in the opening code fence now has an explicit CLI route to
an existing runtime owner. Organism `orgwalk -n` is distinct from the
existing GameForge `walk -n N` or `walk --steps`. Both are now
independently dispatched and tested. `doctor` continues to invoke
the already-dispatched GameForge doctor.

`dump --hot` inspects the hot-file card;
`dump --force` explicitly allows a backup rotation. All repeatable
mutation loops use finite enforced limits; `--help` reports their options.

This resolves operator command routing for the listed verbs, not complete
app-wide UX, security, gameplay, or deployment acceptance.

The `wiki SELECT` verb now routes directly into
`skeleton.galaxy.query.run` (canonical Hoag atom query). It returns
citation/topic handles, not article bodies; `--limit` is enforced in
`1..128`, and query length is bounded to 4096 characters before organism
initialization. No dynamic SQL or arbitrary command execution is used.

## Repeated playable walkthrough contract

`python -m skeleton walk -n N` and `--repeat N` perform 1–100 bounded real
GameForge walkthrough attempts (not organism `orgwalk` cycles). Each attempt
uses a deterministic, distinct seed (`walk:000`, `walk:001`, … or
`<seed>:000`, …). `walk --all-eras -n N` covers each era N times.

`--json` reports individual attempts and aggregates; any failed attempt makes
the command exit unsuccessfully. A single walk without `-n` preserves its
historical output and seed semantics. This behavior was merged in #3756.
