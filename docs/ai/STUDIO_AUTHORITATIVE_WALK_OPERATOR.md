# Source-bound offline walk sessions — operator CLI

This change extends canonical `scripts/studio_ecosystem_cli.py` with an explicit
`--play-walk` mode for authoritative walkable 2D original game sessions. It
uses the same `read_blueprint()` registry as the existing quest CLI and the
same deterministic `studio_ecosystem_walk_replay` engine as other gameplay
consumers. This is not a native genre engine, real-world evidence, or release
certification.

```sh
python scripts/studio_ecosystem_cli.py \
  --project studio_arena_fighting_glacial_fjord --play-walk \
  --walk-events '[["move","right"]]' > walk-save.json

python scripts/studio_ecosystem_cli.py \
  --project studio_arena_fighting_glacial_fjord --play-walk \
  --walk-receipt-stdin \
  --walk-events '[["move","right"]]' > walk-next.json < walk-save.json
```

`--walk-events` accepts a JSON array of `["move", "up|down|left|right"]` and
`["choose", "<authored alternative>"]` pairs. The output is **only** the
canonical JSON session receipt, suitable for private persistence and future
`--walk-receipt` or `--walk-receipt-stdin` restore. Standard input avoids
operating-system command-line length limits for long sessions. An empty
`--walk-events` array exports the current state. The CLI does not write or overwrite filesystem paths itself; users
control redirection, storage permissions, and deletion. Do not place private
playthroughs in the source repository.

Every resume rejects unknown projects, mismatched source digest, altered
position, forged choices, invalid move/collision, unearned certification,
duplicate JSON fields, and history outside the configured count/byte limits.
The engine replays from authoritative source; a client-supplied receipt never
becomes an authorization token or trusted position. The CLI rejects ambiguous
mode combinations and malformed JSON before attempting source compilation.

Validation must include deterministic save→restore→continue, both completed
and partial authored scenes, stale-source and tampered receipt rejection,
resource-exhaustion admission, and exact-head repository CI. These checks
provide **sandbox replay assurance only**, not production release readiness.

## Deterministic interaction route

Add `--walk-route` to `--play-walk` to emit a JSON object with the normal
`receipt` and a source-bound `route`. The route gives shortest cardinal moves
from the verified current position to a cell within interaction distance of
the current authored marker. It reports `locked`, `completed`, `unreachable`,
`already_near`, or `ready` explicitly, and never fabricates a route through
walls or an unavailable quest stage. Tie-breaking is deterministic
(up/right/down/left); traversal is bounded to 4,096 grid cells.

Example: `python scripts/studio_ecosystem_cli.py --project <id> --play-walk --walk-route`

The route digest binds the proposed moves to the source and session receipt;
it is not an authorization token or evidence of a native engine.

## Verified route execution (opt-in)

`--walk-follow-route` follows the shortest verified movement path to the next
authored interaction marker, and emits `receipt` plus `route_execution`. It
never chooses a narrative alternative or advances a quest stage. The operator
can resume from the emitted receipt, inspect the authored alternatives, and
choose explicitly in a subsequent invocation. It is mutually exclusive with
`--walk-route` (hint only). An unreachable, locked or completed scene fails
without a new receipt. The route is admitted against the entire history budget
before a single authoritative replay, then independently checked for source,
scene, choices and destination consistency. The proof binds before/after
session digests, the original route digest and the actual movement sequence.

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk --walk-follow-route > approached.json
```

The proof does not assert native runtime, external evidence or release
qualification. Do not use route execution as a gameplay completion signal.

## Non-mutating authored choice preview

Use `--play-walk --walk-preview-choices` when standing at an authored scene
marker (possibly after `--walk-follow-route` in a previous invocation). The
CLI returns the unchanged authoritative `receipt` and a `choice_previews`
object. Each available alternative is simulated as **one** source-verified
choice with a predicted next scene and successor session digest. No choice is
committed; no save state is mutated. `locked`, `distant`, `completed` and
`budget_exhausted` statuses return no executable alternatives. A preview
cannot prove ending eligibility, original game completion, native gameplay,
or external-world evidence.

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk \
  --walk-receipt-stdin --walk-preview-choices < receipt.json
```

Use the inner `receipt` object from a previous structured response when
resuming; do not feed the whole `approached.json` envelope as a saved receipt.
The route and preview flags are mutually exclusive, keeping each operator
invocation explicit and deterministic.


## Bounded authored branch forecast (no gameplay mutation)

`--play-walk --walk-forecast` predicts source-bound alternatives up to two
scenes ahead, including actual collision-checked movement routes. Optional
`--walk-forecast-depth 1..3` changes the horizon. Each branch includes the
original scene ID, chosen alternative, shortest physical route and replayed
result digest. The caller's save receipt remains unchanged. The engine admits
no more than 24 forecast nodes, and `complete_enumeration=false` explicitly
means that some alternatives were omitted; a partial forecast must never be
presented as an exhaustive ending catalog. Locked, unreachable and exhausted
paths are identified rather than invented. The forecast does not execute a
choice, claim native game completion, or certify external evidence.

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk \
  --walk-forecast --walk-forecast-depth 2
```

The forecast flag is mutually exclusive with route hints, route execution
and single-choice previews. It uses the same canonical authored-world source
and replay admission limits, not a second gameplay engine.


## Commit a forecast branch (authoritative gameplay)

After inspecting `--walk-forecast`, use `--walk-commit-forecast-branch INDEX`
with the same `--walk-forecast-depth` and the **same saved receipt** to execute
one of the ordered branches. Example:

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk \
  --walk-receipt-stdin --walk-commit-forecast-branch 0 \
  --walk-forecast-depth 2 < receipt.json > next-receipt.json
```

The CLI returns a new authoritative `receipt` and a `branch_execution` proof.
It **recomputes** the bounded forecast from current source, collision-checks
every move, replays every authored choice, and verifies intermediate and final
digests before returning a save. It does not accept client-provided forecast
steps as executable authority. Stale receipts, invalid indices, unreachable
routes, exhausted event budgets and source drift fail closed without mutating
the input receipt. The index is stable only for the same source, session and
forecast depth; the proof binds these values and discloses partial enumeration.
An exhausted or locked branch with no choices cannot be committed. The result
is a sandbox replay, not native genre or device certification.


## Source-verified narrative continuity (read-only)

`--play-walk --walk-continuity` emits the ordinary authoritative save receipt
and a deterministic `narrative_continuity` audit. The audit binds the played
stage/choice history to the canonical quest DAG, scene IDs, earned *sandbox*
rewards and authored ending requirements. It reports the next route status,
ending predicates still unmet and whether the source-authored stages are
complete. It never chooses a new action, awards real-world evidence, or changes
an existing save. For example:

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk \
  --walk-receipt-stdin --walk-continuity < saved.json > continuity.json
```

The CLI rejects continuity combined with route execution, choice previews or
forecast commitment. Source digest drift, forged saves, reordered stages,
scene/quest disagreement, and unearned ending predicates fail closed. A
`sandbox_eligible` ending is an authored logical predicate, not a verified
narrative conclusion, native game qualification or release approval.

## Compare two source-verified authored playthroughs (read-only)

`--play-walk --walk-compare-events '<full alternative event history>'` compares
an existing verified save (optionally supplied with `--walk-receipt` or
`--walk-receipt-stdin`) to a second, independently replayed sequence of
movement and authored choices. It returns the unchanged current `receipt` and
a deterministic `comparison` receipt with first divergent event, common
prefix length, source/session digests, authored choice divergence and resulting
positions. The alternative is a *complete* history, not a suffix to append.

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk \
  --walk-receipt-stdin --walk-compare-events '[["move","right"]]' < save.json
```

A movement fork is not automatically an authored narrative fork; separate
`same_authored_choices` and `choice_fork` fields prevent that confusion. Both
histories must pass the same bounded, authoritative replay. Forged/stale saves,
invalid alternative actions, oversized input and ambiguous modes fail closed.
No comparison changes a save, grants an authored reward, certifies a native
runtime, or proves an external-world event. This comparison is a deterministic
sandbox diagnostic, not a release approval.

## Reopen an authored decision without mutating the original save

Use `--play-walk --walk-receipt-stdin --walk-rewind-choices N` (1..32)
to create a new authoritative save immediately before the Nth-most-recent
authored decision. The restored position is the actual last pre-choice
position, not an invented teleport. All subsequent moves, decisions,
scene progress and sandbox rewards are discarded from the new branch.
The original save is unchanged and can be retained separately.

The output contains `receipt` and a deterministic `choice_rewind` audit
with before/after digests, removed event/choice counts, source identity,
and reopened stage ID. A valid previous receipt is mandatory; combining
rewind with new events or other walk analysis modes is rejected. Rewinds
are bounded, replay-verified, source-bound and are **not** native runtime
or release evidence. Never overwrite a private save automatically.

## Source-verified authored scene timeline and checkpoint restoration

`--walk-timeline` inspects a verified current session and prints a bounded
`timeline` alongside the unchanged `receipt`. The timeline includes genesis
and up to 32 most-recent completed authored scene checkpoints, with stable
absolute checkpoint indexes, stage IDs, chosen alternatives, positions, source
and session digests, and deterministic checkpoint/timeline digests. An omitted
checkpoint is **not** silently represented as verified: `omitted_checkpoint_count`
is explicit. The index is a navigational identifier, not an authorization
credential. The aggregate source replay budget is 16,384 events across listed
non-genesis checkpoints. This bounds expensive repeated world compilation and
avoids a large response for a long playthrough.

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk \
  --walk-receipt-stdin --walk-timeline < verified-save.json

python scripts/studio_ecosystem_cli.py --project <id> --play-walk \
  --walk-receipt-stdin --walk-restore-checkpoint 1 < verified-save.json \
  > restored-checkpoint.json
```

`--walk-restore-checkpoint` requires an existing saved receipt, disallows
appending actions in the same invocation, and accepts only an absolute index
present in the bounded timeline. It replays the selected authoritative event
prefix, emits a normal restorable `receipt` plus a deterministic
`checkpoint_restore` audit, and does not mutate the original save. Players may
resume from the restored receipt and make different authored choices. Invalid
indices, forged or stale saves, source changes during replay, and mismatched
checkpoint digests fail closed. The CLI never writes save files itself.

This is an offline sandbox checkpoint feature, not a substitute for engine
persistence, game certification, asset-rights verification, or device testing.
Required validation includes restore→continue with a different choice, genesis
and completed checkpoint restore, deterministic receipts, bounded longform
truncation, stale-source and forged-session rejection, and CLI mode isolation.
