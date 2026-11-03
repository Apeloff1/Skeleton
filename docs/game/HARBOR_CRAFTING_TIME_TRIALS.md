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
