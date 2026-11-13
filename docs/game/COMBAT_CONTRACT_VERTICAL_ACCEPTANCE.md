# Combat contract: end-to-end playable acceptance

Run `python -m skeleton game-vertical-accept demo --kind combat_contract`
to exercise an original authored combat contract through the canonical turn
engine. The acceptance gate checks complete execution, checkpoint replay at
a selected action boundary, objective completion, earned credits/inventory,
and export/import of the exact source-bound final save.

The `run`, `verify`, `export` and `import` commands use the existing
strict JSON acceptance format. A forged action, reward, winning phase, save
or portable checksum fails replay. Acceptance receipts prove deterministic
functional consistency, not publisher identity, device qualification or
release readiness.
