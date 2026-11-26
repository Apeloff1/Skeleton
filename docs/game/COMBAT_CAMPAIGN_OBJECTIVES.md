# Combat campaign objectives — playable offline vertical

The `combat-objectives` command adds authored objectives and earned score to the
canonical turn-combat campaign. It never edits combat outcomes, health or
campaign currency. Each objective is bound to an authored encounter and is
evaluated only after the canonical replay completes that encounter.

## CLI

```sh
python -m skeleton combat-objectives demo
python -m skeleton combat-objectives start --source-json '{"schema_version":"skeleton.combat_objectives.v1",...}'
python -m skeleton combat-objectives advance --session-json '<checkpoint>'
python -m skeleton combat-objectives finish --session-json '<checkpoint>'
python -m skeleton combat-objectives verify --session-json '<checkpoint>'
python -m skeleton combat-objectives summary --session-json '<checkpoint>'
python -m skeleton combat-objectives pack --session-json '<checkpoint>'
python -m skeleton combat-objectives unpack --package-json '<package>'
```

Source uses `skeleton.combat_objectives.v1` with canonical `campaign` and
1–16 `objectives`. Each objective declares `objective_id`, `encounter_id`,
`kind` (`victory`, `survive`, `currency`, `final_victory`),
`threshold`, `points`, and `requires`. Dependencies must target earlier
encounters, preventing circular unlocks and same-encounter reward laundering.

All inputs use strict bounded JSON. Score is capped and derived solely from
verified combat journal entries; a forged snapshot, checkpoint lineage, reward
or portable manifest fails replay equality. `summary` distinguishes
`pending`, `completed`, `failed`, `blocked` and `unreachable`.
Checkpoint and portable digests detect corruption; they do not authenticate
the author. Applications must enforce authorization and provenance separately.
No hardware or consumer release qualification is implied.
