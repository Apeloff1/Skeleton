# Source-bound combat balance and replayable victory witnesses

The canonical offline game builder can author an encounter that is valid but
unwinnable for a player. `combat-balance` explores legal actions for one
player-controlled team while all other teams follow the existing versioned
tactical policy. It does not execute authored scripts or contact a provider.

## Run

```sh
python -m skeleton combat-balance demo
python -m skeleton combat-balance analyze --scenario-json '{"schema_version":"skeleton.turn_combat.v1","world_id":"glass_moor","encounter_id":"bridge_watch","turn_limit":16,"actors":[{"id":"scout","team":"wayfarers","max_hp":12,"attack":5,"defense":2,"speed":3},{"id":"warden","team":"reedbound","max_hp":7,"attack":3,"defense":1,"speed":2}]}' --team wayfarers --max-states 512 --max-turns 16
python -m skeleton combat-balance verify --report-json '<entire report JSON>'
python -m pytest skeleton/testing/test_combat_balance.py
```

The output includes canonical authored source and its digest, team, policy
version, search limits, explored-state/transition counts and a deterministic
checksum. A `victory_witness` carries legal ordered actions and the final
save/state digests. The verifier reruns the bounded search and the witness
through the canonical save/replay engine. Receipts are checksums, **not
cryptographic signatures or authorization**.

`exhaustive_no_witness` means no victory exists **within the authored
turn limit and fixed opponent policy**, provided all reachable states were
explored without hitting the configured bounds. This does not prove fairness,
human difficulty, multiplayer safety or victory against different policies.
`inconclusive_budget` means the state, turn or transition budget truncated
exploration; it is never mislabeled as an unwinnable encounter.

The state space is deduplicated by the canonical deterministic state digest,
not by untrusted player claims. Search order is stable and attacks, guard and
rest are all explored. No save is mutated in place. The analyzer caps states
at 4096 and analysis turns at 32, with an independent transition cap.
Malformed source, unknown teams, noninteger budgets, noncanonical JSON,
forged receipts and unsupported policy versions fail closed.

## Integration and acceptance

`python -m skeleton combat-balance` is a first-class CLI command.
Authored source is normalized by `turn_combat.normalize_scenario`; moves
are executed by the production `_advance` transition; every winning
session is replay-verified by `verify_session`; saved witness digests
are checked against `resume_session`. This enables a creator to run a
pre-publication playability diagnostic without inventing combat results.

The exhaustive guarantee assumes the current deterministic opponent policy
and exact canonical combat semantics. A changed policy must change the
policy version and invalidate old reports. Independent game/consumer
qualification and provenance controls remain required.
