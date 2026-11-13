# Lantern Quay — replay-certified time trials

Time trials are authored JSON courses tied to a single original world. The
course at `skeleton/game/gameplay/fixtures/harbor_lantern_quay_time_trial.json`
requires the player to enter four checkpoints **in order**, before their
individual deadlines, then deliver cargo and earn the `signal` ending. The
gold, silver and bronze thresholds use canonical action ticks, not wall-clock
time or client-supplied scores.

Run `python -m skeleton.game.gameplay.harbor_crafting_cli demo --require-win > save.json`.
Then run `python -m skeleton.game.gameplay.harbor_crafting_cli trial-run --bundle save.json --trial skeleton/game/gameplay/fixtures/harbor_lantern_quay_time_trial.json --require-win > trial.json`.
Verify a portable report using `python -m skeleton.game.gameplay.harbor_crafting_cli trial-verify --report trial.json --require-win`.

For interrupted play, use `trial-resume --bundle save.json --actions
continuation.json --expected-terminal-digest DIGEST --trial COURSE`; the
underlying canonical save is re-executed and CAS-checked before scoring.
For multiple verified finishes, provide a JSON array of reports to
`trial-leaderboard --reports runs.json`, and check its exported result using
`trial-verify-leaderboard --board scoreboard.json`.

Incomplete or wrong-choice runs produce `status=incomplete` with no medal,
unless `--require-win` demands a finished course and fails closed. Invalid
course geometry, duplicated checkpoints, expired checkpoints, tampered replay
events, stale continuation leases, fabricated medals, duplicate entries and
mixed-course scoreboards are rejected. Search, event, input and report sizes
are bounded by the existing world and save limits.

**Trust boundary:** these proofs establish deterministic gameplay consistency
against included source data, not cryptographic identity, tournament fairness,
copyright provenance, or device/release qualification. A user can author a
different valid run; identity-signed competitive submissions require a separate
trusted server. No scoreboards or medals are used to authorize releases.

## Transactional course editor

Use `trial-author --trial COURSE --trial-edits edits.json
--expected-course-digest DIGEST --expected-source-digest SOURCE_DIGEST
--preview-bundle save.json > revision.json` to author a complete course
transaction. The optional preview replays real player actions against the
revised course, and can downgrade a previously earned medal. Edit operations
are `set_deadline`, `set_medals`, `set_choice`, `set_checkpoint`,
`append_checkpoint`, and `remove_checkpoint`. Each operation has a fixed
typed shape, and the whole transaction is rejected if the final course is
invalid. Run `trial-verify-author --trial-revision revision.json` to
reconstruct the edit transaction and its optional gameplay preview.

Both the original source digest and original course digest are optimistic
concurrency leases. No authored edit is allowed to rewrite an existing save,
forge a medal, or silently substitute a different world.

## Interactive time-trial play

Run `python -m skeleton.game.gameplay.harbor_crafting_cli trial-live
--trial skeleton/game/gameplay/fixtures/harbor_lantern_quay_time_trial.json`.
The regular terminal controls are available: `north`, `south`, `east`,
`west`, `gather`, `craft ID`, `trade ID`, `deliver`, `signal`,
`shelter`, `hint`, `undo`, `redo`, `save`, and `quit`.
`hint` reports both canonical legal actions and earned checkpoint progress.
A normal story victory does **not** imply a successful time trial: a missed
checkpoint or wrong ending returns a nonzero exit status with a replayable
`TRIAL_REPORT` and `CHECKPOINT`, never a fabricated medal.

## Replay ghosts and side-by-side movement

`ghost-race --bundle player.json --ghost-bundle ghost.json --trial COURSE
--expected-terminal-digest PLAYER_TERMINAL_DIGEST > race.json` compares a
real player save with a separately verified, **completed** time-trial ghost.
It exports each participant's canonical position at every tick, ordered
checkpoint time deltas, finish-time delta, and earned leader. The ghost is
observational: it never becomes a collision obstacle or changes game state.

`ghost-verify --report race.json` rebuilds both gameplay histories and the
complete timeline. Partial player runs remain visible but cannot win. Mixed
worlds, unfinished ghosts, stale player checkpoints and forged positions or
scores fail closed. These are replay proofs, not signed player identities.
