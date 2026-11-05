# Scene Market Fork — Replay-Proven Player Choices

`python -m skeleton scene-market-fork demo` previews two original alternatives:
a complete earned-currency/crafting/delivery run and a purchase attempted before
the player earns currency. The latter is marked **blocked**, never silently
executed or counted as a win.

## Player workflow

1. Create or resume a canonical `scene-market` checkpoint.
2. Call `scene-market-fork evaluate --session-json '<checkpoint>' --candidates-json
   '<list>'` with at most 12 distinct candidates, at most 24 actions per
   candidate and at most 96 total actions.
3. Inspect `outcomes`: accepted alternatives include canonical phase, credits,
   reputation, delivered objectives, tick and state digest; rejected actions
   carry the first blocked step and reason, without a fabricated state.
4. Call `scene-market-fork verify --report-json '<report>'` to replay every
   alternative from the original checkpoint, including the claimed rejection.
5. Call `scene-market-fork choose --report-json '<report>' --candidate-id
   '<accepted-id>'` to obtain a canonical, restartable market save. A blocked
   alternative cannot be committed.
6. Use `scene-market-fork export` / `import` to carry the preview and its
   checkpoint between offline devices; the import reconstructs the witness.

## Trust and limits

The canonical scene-market reducer is the sole authority for coin pickups,
stock, crafting, delivery, collision and endings. Previews do not mutate the
input checkpoint. Candidate ordering is canonicalized by ID; a deterministic
heuristic favors replayed victories, then objectives, reputation, remaining
credits and shorter routes. It is **not** an optimality proof.

The report contains source and state digests, a complete canonical checkpoint,
the bounded alternatives and a recomputable checksum. A checksum detects
accidental changes but is not a MAC or signature; hostile sources must still be
validated against trusted provenance at the application boundary. No network,
filesystem writes, external clocks or random numbers are used by the reducer.
Malformed JSON, duplicate keys, non-finite numbers, forged receipts, unknown
actions and unearned purchases fail closed. Every branch can be re-executed
independently from the same checkpoint; no speculative branch is authoritative
until a player explicitly selects an accepted alternative.

Focused tests: `python -m pytest skeleton/testing/test_scene_market_fork.py -q`.
