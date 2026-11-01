# Readable Tactical Control-Point Board

`python -m skeleton arena-control-render demo` displays the original
Lantern Harbor match as a JSON-encoded ASCII board. A wall is `#`, an
empty tile is `.`, numbered capture zones use `1` through `8`, and
living actors use stable `A` through `P` glyphs. The legend lists each
actor's identity, team, HP and position, plus each zone's source ID and
points. Dead actors remain in the legend but do not occupy a tile.

`render --session-json ...` replays the complete checkpoint before
drawing. `verify --session-json ... --render-json ...` independently
regenerates the board and rejects altered scores, glyphs, actor health,
wall positions, text or receipts.

The interactive capture command emits the same verified board at each
player turn. This is an accessible text UI, not a claim of 3D graphics,
network multiplayer authority or device rendering qualification.
