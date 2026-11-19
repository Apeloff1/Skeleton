# GameForge saga — recovered championship engines and bounded recovery

The fixed advanced-owner surface now binds five canonical gameplay kinds
to generated objectives. These are source-level integrations of existing
engines, not new implementations of the local combat or economy rules.

| Owner kind | Rule fields | Earned gate |
| --- | --- | --- |
| survey_expedition | survey, weather, dialogue, required_ending | required survey, permit and ending |
| convoy_contract | convoy, contracts, choice | earned escort and contract outcome |
| convoy_league | league, quests | championship and cross-round quests |
| timed_season | season, minimum_points | all authored courses and total earned points |
| delivery_chain | board | every authored delivery order |

## Round-scoped gameplay

The three multi-round owners use explicit local actions:

```json
{"type":"episode","objective":"s3","action":{"op":"round","round":"canal_relief","action":{"op":"move","direction":"east"}}}
```

Round identifiers are source-authored, never inferred from a client's
current score. No later round can start before actual prior earned
completion. Each round gets its own canonical inventory and route history.
A terminal course or delivery that fails the authored owner's scoring/rule
admission remains a real terminal local run, without credit or permission
to move to the next round. The league preserves its own hull, bounty,
score, maximum total ticks, and quest prerequisites.

The timed-season adapter retains canonical partial-run bundles and
submits completed runs to the existing season owner. All awarded medals
and points are recomputed. The order-chain adapter similarly submits
actual completed runs to the existing contract save owner; no deadline
or action-count rule is duplicated. The source can supply explicit
witnesses. The existing league and delivery solvers can also generate
witnesses via saga authoring. Timed seasons require an explicit witness.
None of these authoring operations pre-populates a player's ledger.

The compact board reports the current round and actual standings.
League quest points, season medals and earned delivery counts are distinct
local units. The terminal player exposes them, not fabricated global money.
Full evidence remains an independently rebuilt report; documents that
exceed the existing common JSON or owner-specific bounds are rejected.

## Advanced recovery

The outer recovery planner retains the original bounded dialogue and
crafting/mission search. Each advanced owner first tries its authored
witness suffix and up to four verified wait-splice alignments (including
round-scoped waits). If those do not work, the advanced planner searches
exact action histories against the fixed canonical replay adapters.

- Explicit maximum retained states: 1–128 (default 32).
- Explicit maximum transition attempts: 1–512 (default 128).
- The limits are per unfinished advanced episode; previous dialogue and
  local crafting budgets remain separate.
- Rejected canonical transitions also consume an attempt.
- Every accepted history is replayed, and a successful proposal must
  independently reproduce its reported local completion digest.
- No approximate inventory-only equivalence is used to merge distinct
  histories. Survey, weather, conversation and contract consequences
  can depend on the action history.
- Priority ordering is heuristic. Exhaustion is not an optimality or
  impossibility result, and no automatic action is applied.

`assist` and `assist-slot` accept two additional optional fields:
`advanced_states` and `advanced_attempts`. They are included in the
recovery receipt and independently checked by its verifier. Full search
on arbitrary advanced scenarios remains bounded by actual source limits
and the supported candidate actions. Large search costs need physical
performance qualification.

## Journal correction

Schema creation, reads, writes and foreign keys now all use the exact
same fixed namespace mapping. Earlier source accidentally created the
campaign namespace even for expedition and saga adapters. The new
regression creates and reopens all six expected tables and checks that
each revision foreign key points to its own namespace. No old campaign
table is removed, renamed, or automatically migrated. This repair does
not imply any prior deployed database was qualified.

## Focused qualification

```sh
python -m pytest -q skeleton/testing/test_gameforge_saga_rounds.py skeleton/testing/test_gameforge_saga_league.py skeleton/testing/test_gameforge_saga.py skeleton/testing/test_gameforge_expedition.py skeleton/testing/test_gameforge_campaign.py
python -m compileall -q skeleton/app/gameforge_saga_league.py skeleton/app/gameforge_saga_rounds.py skeleton/app/gameforge_saga_search.py skeleton/app/gameforge_saga_owners.py skeleton/app/gameforge_saga_board.py skeleton/app/gameforge_saga_author.py skeleton/app/gameforge_saga_live.py skeleton/app/gameforge_saga_cli.py skeleton/app/gameforge_campaign_store.py
```

Run the existing league, league quest, timed trial, season, delivery
contract, solver and journal suites before claiming integration parity.
Clean-wheel installation, final-head mandatory CI, physical storage,
recovery, backend and graphical/native device tests remain separate.
No merge, release, or native qualification is asserted.
