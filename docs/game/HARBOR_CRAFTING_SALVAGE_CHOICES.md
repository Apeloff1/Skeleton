# Earned salvage championship endings and consequences

A completed, replay-verified championship may choose among original authored
epilogues. The authored board offers rebuilding the community quay, a merchant
charter, or a future rescue fleet. The last option requires a higher score and
is not available after the canonical two-round score of 36.

The choice system verifies every source-bound salvage round and earned
championship score before granting an ending. Points spent and reputation are
derived from the selected authored choice; they do **not** mint canonical
currency or mutate a previous save. Alternative choices are deterministic
branches over the same immutable earned season, not rewrites of history.

Use `python -m scripts.game.harbor_salvage_choices --help`. The `choose
--save season.json --choice rebuild_quay` command produces a portable report.
`verify --report choice.json` independently replays it. `compare --save
season.json` shows earned and unearned alternatives. `author --save
season.json --edits edits.json --expected-board-digest SHA` applies
transactional, source-validated edits and can preview a previously earned
choice. `package --save season.json`, `play --package package.json --choice
merchant_charter` and `verify-play` close the export/replay path.

All inputs are bounded, strict JSON. Unknown choices, stale authoring leases,
unearned score thresholds, duplicate IDs, unsupported fields, invalid
epilogues and tampered reports fail closed. The package is digest-checked, not
signed or authenticated; exact-head CI and device qualification remain open.
