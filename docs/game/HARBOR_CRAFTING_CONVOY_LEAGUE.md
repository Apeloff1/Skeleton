# Lantern Quay convoy league — playable, source-bound championship

The league is an original two-stage escort championship. Every stage invokes the
existing canonical Lantern Quay movement, gathering, crafting, merchant, and
convoy combat runtime. Each stage has its own independently replayed action log,
hull integrity, earned weapon charges and bounty. Player resources reset between
stages deliberately; the league awards standings, not fabricated inventory.

The authored league board binds to the canonical world identifier and to a
distinct, validated convoy board per round. It sets minimum earned bounty and
remaining hull for each round, an overall score target and a total tick budget.
The engine rejects duplicate boards, duplicate round names, invalid numeric
values, unsafe source mismatches and progression past unfinished rounds.

A round earns points only when its convoy reaches the dock and its bounty/hull
requirements are satisfied. Points = earned bounty + 2 × remaining hull.
An unsuccessful completed round or a destroyed convoy ends the league. A player
who completes all rounds but misses the authored score target also loses.
No replay or authored edit can turn an unearned ending into a victory.

The portable save contains canonical source, authored board, player actions,
replay-verified convoy reports, standings and source/board/save digests.
Verification replays every convoy round and reconstructs the entire save, not
just the stored hash. Resume requires an exact digest lease and rejects terminal
saves, stale leases, history rewrites and oversized inputs. Portable packages
bind the authored world and league to an ID and replay package plays independently.
The authoring editor uses CAS leases, bounded operations, and replayed previews.

## Commands

Run the module `python -m skeleton.game.gameplay.harbor_crafting_cli`.

- `league-init --league-board PATH` creates an empty playable save.
- `league-run --league-board PATH --sessions PATH` plays authored action arrays.
- `league-verify --league-save PATH` independently replays the saved run.
- `league-status --league-save PATH` reports score, earned rounds and next stage.
- `league-resume --league-save PATH --actions PATH --expected-league-digest SHA`
  advances the active stage or begins the next stage under an optimistic lease.
- `league-live --league-board PATH` runs the interactive convoy terminal for
  each stage, returning a portable league save on stdout.
- `league-package-build --league-board PATH` exports an original playable package.
- `league-package-play --league-package PATH --sessions PATH` plays that package.
- `league-package-verify-play --league-play PATH` replays package and game.
- `league-author --league-board PATH --league-edits PATH
  --expected-league-board-digest SHA` makes transactional authoring edits.
- `league-verify-author --league-revision PATH` replays editor changes.

The checked-in example is
`skeleton/game/gameplay/fixtures/harbor_lantern_quay_convoy_league.json`.
Run the convoy test suite for source→game→save→replay→package→CLI acceptance.
Security and device qualification are separate release gates.

## Tactical source authoring

The transactional league editor also supports `encounter-strength` and
`encounter-reward` edits targeting `round_id:enemy_id`, plus
`convoy-hull` and `convoy-max-turns` edits targeting `round_id`.
These change the actual authored combat and escort rules, not just the
displayed score. Each revision revalidates the complete source-bound league
and, when a preview save is supplied, replays every prior player action under
the proposed new rules. If the edited enemy strength makes a previously won
route unwinnable, preview publication fails closed rather than certifying an
unearned victory.
