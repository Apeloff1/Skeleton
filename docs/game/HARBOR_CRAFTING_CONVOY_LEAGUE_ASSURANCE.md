# Convoy league — source-to-victory assurance

The league solver composes the existing bounded canonical convoy solver per
authored round and requires a complete championship before publishing a plan.
The solver does not skip movement, crafting, NPC collision, combat or the
authored bounty and hull requirements. Each plan is replay-verified.

The append-only journal persists only normalized player action segments, a
package, ancestry hashes, and independently replayed save/play digests.
Every append is an optimistic compare-and-swap transaction, and every
historical read replays the selected prefix. Diverged histories are not
automatically merged; fast-forward requires a strict ancestor and an exact
journal lease. Bounded entry/action budgets prevent unbounded replay.

The leaderboard verifies every completed league save, rejects mixed source
and authored league identities, ranks by earned score then fewer ticks then
player identifier, and replays the entire ranking during verification.

The acceptance receipt recomputes the solver, package, journal, ranked
standings and original gameplay. It stores only source, authored rules,
player actions, component digests and a small summary. A resealed forged
score or altered action log is rejected on replay.

Use the CLI commands `league-solve`, `league-verify-plan`,
`league-journal-init`, `league-journal-append`,
`league-journal-verify`, `league-journal-at`,
`league-journal-compare`, `league-journal-fast-forward`,
`league-board`, `league-board-verify`, `league-accept`, and
`league-verify-accept`. See HARBOR_CRAFTING_CONVOY_LEAGUE.md for
source and package commands. No device/release qualification is implied.
