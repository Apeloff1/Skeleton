# Bounded offline combat-contract route solver

`python -m skeleton combat-contract-solve demo` searches legal turn-combat
actions in deterministic breadth-first order. `run --source-json JSON`
accepts authored missions, with `--max-depth 1..16` and
`--max-nodes 1..3000`. The solver supports at most four actors per
encounter and refuses oversized search frontiers instead of returning an
unproven route. The report includes the original source digest, exact actions,
expanded-node count, replay-verified terminal contract, and portable bundle.
`verify --report-json JSON` recomputes the same bounded search and rejects
altered paths, objective claims, rewards, receipts or bundles.

Equivalent combat states are deduplicated using HP, guard flags, turn index,
tick, objective state and partial player-team guard counts; journal checksums
are not used as game-state identities. A mission that wins combat without
meeting every authored objective is not an earned solution. This is a
bounded planning tool, not a proof of globally shortest play beyond the
configured legal action set and search budget.

Run `pytest -q skeleton/testing/test_combat_contract_solver.py`.
