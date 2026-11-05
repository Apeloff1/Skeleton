# Interactive Market Fork — Player Decision Board

Run `python -m skeleton scene-market-fork-play demo` and send a single JSON
line such as `{"candidate_id":"complete_delivery"}`. The first output line
lists each replay-proven alternative, its blocked/accepted status, source and
checkpoint digests, and a deterministic heuristic recommendation. The player
may ignore the heuristic; only an explicit accepted selection commits a game.

`scene-market-fork-play play --report-json '<fork-preview>'` accepts any
canonical preview created by `scene-market-fork evaluate`. A successful
selection emits a portable canonical game bundle that can be imported using
`scene-market import`. Invalid choices return a JSON rejection without
changing the checkpoint. After three rejected attempts, EOF or oversized
input, the tool emits a portable preview checkpoint before returning an
error; the player can resume later using `scene-market-fork import`.

This terminal is intentionally offline and deterministic. No speculative
branch spends currency, claims a delivery, changes health or mutates the
source checkpoint. All decisions are validated against canonical replay.
