# Weather route solving and player board

The production weather layer now exposes read-only canonical gameplay actions,
deterministic forecast and earned inventory through
`python -m skeleton scene-weather-board demo`. For a saved session use
`scene-weather-board inspect --session-json JSON`. The board checks actions
with the same weather reducer as interactive play. A legal action is not a
promise of eventual victory.

`python -m skeleton scene-weather-route demo` runs bounded route search.
Use `scene-weather-route solve --source-json JSON --max-states 512
--max-depth 24`, or pass a verified checkpoint with `--session-json`.
A successful `proven_win` receipt includes replayable actions, source and
initial-state digests, terminal state digest and a portable bundle checksum.
`scene-weather-route verify --session-json JSON --proof-json JSON`
recomputes the same bounded search and independently replays the result.

Search exhaustion is always `inconclusive`; it never establishes that an
authored level is impossible. Gear cannot be equipped before its original
pickup, collision is delegated to the canonical tile engine, stamina and
weather are evaluated at each actual action tick, and portable checksums
detect accidental corruption but are not cryptographic signatures.
