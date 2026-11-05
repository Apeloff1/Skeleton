# Source-bound mission league scoring author

The installed command `python -m skeleton scene-mission-league-author`
provides transactional scoring edits for original offline playable missions.

`demo` creates a new, empty Lantern Harbor mission league and changes the
victory bonus from 200 to 250. `edit --league-json JSON --edits-json JSON
--expected-digest DIGEST` applies at most 16 unique numeric scoring fields
with an exact optimistic compare-and-swap guard. The result includes both
verified source-bound league states, canonical ordered edits and a replayable
authoring receipt. Invalid fields, booleans, no-op changes, out-of-range
scoring and stale revisions are rejected.

`preview --receipt-json JSON --actions-json JSON` executes the actual
mission director using the edited source, verifies a completed ending and
computes a score using the canonical league engine. Preview cannot mint
rewards or alter the published league.

`verify`, `export` and `import` recompute authoring receipts and check
bounded portable JSON integrity. Once any real attempt is submitted, scoring
rules are immutable; authors must create a new league rather than rewrite
earned historical standings. Source provenance and player identity remain
external requirements; checksums are not signatures. This is not a hosted
leaderboard, network identity provider or release certificate.
