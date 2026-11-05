# Original salvage scene renderer and asset editor

The scene renderer reconstructs every visited tile from canonical movement,
NPC patrols and replay-verified salvage actions. Unknown cells remain under
fog-of-war; full-map reveal is permitted only after the player earns rescue.
Original authored ASCII glyphs and site descriptions are strictly validated,
source-bound, finite, and never executed or fetched as external content.

`python -m scripts.game.harbor_salvage_map --help` exposes:
`render --report report.json`, `verify --view view.json`,
`print --view view.json`, `manifest`, `author`, `verify-author`.
Use `--reveal` only with a completed salvage report. `author --edits
edits.json --expected-assets-digest SHA` supports transactional glyph and
site-label changes, with optional replayed scene preview using `--report`.

Scene views include the exact replay-verifiable game report, authored assets,
player and merchant positions, source-bound map geometry, fog visibility,
status, legend and digest. Reverification recomputes all tiles and refuses
forged frames even when the attacker recomputes a digest. ASCII assets are
original in-repository text, not an attested external rights certificate.
