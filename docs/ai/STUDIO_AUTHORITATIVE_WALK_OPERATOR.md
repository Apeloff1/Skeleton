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

## Source-verified authored choice coverage (read-only)

Use `--play-walk --walk-audit-choices` to verify the alternatives of upcoming
authored scenes against real deterministic walk replay. The auditor checks the
canonical quest/scene continuity contract, physically approaches each authored
marker, then independently executes **every alternative at that marker** from
the same pre-choice state. Only the first alternative advances a single
reference path to the next stage. It does **not** enumerate the Cartesian
product of all branch combinations, prove narrative originality, or certify a
native game. The input save remains unchanged.

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk --walk-audit-choices
```

The receipt includes stage/scene IDs, source/session hashes, per-choice
successor digests, route digests and distances, explicit unverified alternative
counts, and a SHA-256 coverage digest. It stops with an explicit reason for
locked/unreachable scenes, event exhaustion, or the 24-stage, 96-choice and
16,384 replay-work limits. A partial result always reports
`complete_reference_path_coverage=false`; even a complete reference-path
audit reports `all_branch_combinations_verified=false`. Authorization,
source drift, forged saves, malformed choices and inconsistent successors fail
closed. This is a local authoring QA tool, not a release gate or device test.

## Paginated original catalog choice audit

Use `--walk-audit-catalog` for deterministic, read-only authored choice
assurance across the registered source catalog. `--walk-audit-offset N` and
`--walk-audit-batch-size 1..4` select a bounded page; optional `--genre`
and `--biome` filter the canonical index. Each project is read through the
same safe registered source loader, and its authored alternatives are tested
by real collision-checked walk replay. No new save or asset is written.

```sh
python scripts/studio_ecosystem_cli.py --walk-audit-catalog --walk-audit-batch-size 2
python scripts/studio_ecosystem_cli.py --walk-audit-catalog --walk-audit-offset 2 --walk-audit-batch-size 2
```

Pages carry a stable catalog digest, next offset, per-project source/coverage
SHA-256 digests and explicit invalid/partial statuses. Consumers must compare
catalog digests before combining pages. An index changing during the page
fails closed. The result never claims all branch combinations, rights,
artistic merit, native gameplay, external proof or release qualification.

## Typed Jeeves authored choice coverage parity

The existing operator-authorized `studio_authoritative_walk` Jeeves tool
accepts `operation="coverage"` using its versioned request schema and the
same canonical replay authority as `--play-walk --walk-audit-choices`.
The tool recomputes and verifies the saved receipt, checks source identity,
returns the deterministic choice coverage receipt under `detail`, and never
accepts caller-supplied authority or certification flags. A forged receipt,
invalid project or untrusted request fails before any game-state mutation.
The operation is a read-only authoring diagnostic, not a provider call or
native-game certification.

## Typed Jeeves catalog audit

`JeevesGameOrchestrator.authoritative_walk_catalog()` accepts a distinct
versioned `studio_authoritative_walk_catalog` tool request with bounded
`offset`, `limit` (1..4), and optional `genre`/`biome` filters. The tool
rejects unknown fields, invalid numbers, forged authority and oversized
requests before reading the canonical index. It delegates to the same source
assurance engine as `--walk-audit-catalog`, returns index/source/coverage
receipts and never claims a completed original game or release approval.

## Source-bound catalog audit continuation

The paginated `--walk-audit-catalog` operator audit now binds each continuation
page to the exact SHA-256 of the filtered catalog index. The first page
returns `catalog_digest` and a `continuation` object containing the next
offset, page limit and filter values. Supply that digest for every nonzero
`--walk-audit-offset`; do not mix pages from different catalog snapshots.

```sh
python scripts/studio_ecosystem_cli.py --walk-audit-catalog \
  --walk-audit-offset 2 --walk-audit-batch-size 2 \
  --walk-audit-expected-digest <first-page-catalog-digest>
```

Jeeves' typed `studio_authoritative_walk_catalog` request accepts the same
optional `expected_catalog_digest` (64 lowercase hexadecimal characters).
It is mandatory when `offset > 0`. Invalid, absent or stale continuation
identity fails before project source compilation. The catalog is also checked
again after the page audit, so a concurrent catalog change fails closed.
The digest is a source identity, not a secret, authorization credential,
cryptographic signature or release approval. For complete coverage, continue
until `next_offset` is null; each individual page remains bounded to four
projects, and a page receipt never claims native genre certification.

## Source-revalidated aggregation of bounded catalog pages

The CLI `--walk-audit-aggregate-stdin` accepts a JSON list containing one to
four unmodified page receipts from `--walk-audit-catalog`. It reopens the
canonical index and every selected project, repeats source-bound choice replay,
and compares each page to its newly computed authoritative receipt. Forged
coverage, missing or reordered pages, stale source, inconsistent filters,
repeated projects, duplicate JSON keys, nonfinite values and oversized input
fail closed. The input is limited to 128 KiB and no more than 16 projects.

```sh
python scripts/studio_ecosystem_cli.py --walk-audit-aggregate-stdin < pages.json
```

Jeeves exposes the same operation as the operator-authorized typed tool
`studio_authoritative_walk_catalog_merge` with a `pages` array. Its receipt
binds the current catalog digest, exact page audit digests, covered/partial/
invalid counts and next offset. A merge covering only part of the index must
not claim full coverage. Replaying source is deliberate: untrusted client
JSON is never accepted as evidence merely because it carries a digest.
This diagnostic does not certify game completeness, native execution or release.

## Source-bound authored story transcript

Use `--play-walk --walk-story-transcript` with a registered project and,
optionally, a verified save receipt. The CLI emits the unchanged receipt plus
source-verified played scene IDs, authored interaction objects, selected
alternatives and the next scene. This is not generated dialogue or a second
save authority. The transcript discloses omitted entries beyond the 32-scene
presentation limit and binds its content to the session and source digest.

```sh
python scripts/studio_ecosystem_cli.py --project <id> --play-walk --walk-story-transcript
python scripts/studio_ecosystem_cli.py --project <id> --play-walk --walk-receipt-stdin --walk-story-transcript < saved.json
```

No network/provider is used. Forged receipts, source drift, invalid limits and
unauthorized invocation fail closed. A digest is not a signature or native
runtime/release certification. Source-backed tests cover route, choice,
replay, save/restore, forgery and deterministic receipts.


## Paginated authored transcripts and Jeeves parity

For longform played campaigns, `--walk-story-transcript --walk-story-limit 1`
returns a bounded page and `next_offset` with a `continuation_session_digest`.
Continue with `--walk-story-offset N --walk-story-expected-digest SHA256`.
The digest binds continuation to the exact replayed save; changes to played
choices or source invalidate the next page. Pages are source-replayed and do
not mutate the save. `JeevesGameOrchestrator.authoritative_walk()` exposes the
same behavior through operation `transcript` and typed `transcript_offset`,
`transcript_limit`, and `transcript_expected_digest` request fields.
The transcript remains a sandbox authoring diagnostic, not native gameplay proof.


## Source-bound authored canon journal

`--play-walk --walk-canon-journal` presents the era, protagonist, original
scene site/weather, authored plot-beat cause/goal/decision, cast dialogue hook
and possible consequence alongside the verified choices actually played.
It distinguishes authored possible consequences from observed outcomes. Pages
are limited to eight scenes. A continuation requires both the exact session
SHA-256 and an independent digest of the narrative/scene/cast source, so
changing canon between pages fails closed. The typed Jeeves walk tool exposes
`operation=journal` and the equivalent bounded continuation fields.
No provider, native engine or unverified evidence is activated by this read.


## Canon source proof and ending obligations

`python scripts/studio_ecosystem_cli.py --project ID --audit-canon` checks
original era order, quest-to-scene mapping, plot-beat identity, cast dialogue
hooks and critical cast references against the canonical authored blueprint.
Jeeves exposes the same read-only operation through
`JeevesGameOrchestrator.authoritative_canon_proof()` and the typed
`studio_canon_proof` tool schema. Contradictions are explicit deterministic
issue records; unproven ending predicates remain external evidence obligations,
not earned rewards. No authoring audit certifies rights, native gameplay or release.


### Source-leased original canon revisions (Studio A)

The operator-authorized offline CLI supports original prose edits without
mutating registered catalog sources. First obtain the source_digest from
--project PROJECT --audit-canon. Then use --project PROJECT --author-revision
--revision-request JSON --output NEW_DIRECTORY. The typed request contains
schema=skeleton.game_builder.studio_author_revision_request.v1, project_id,
expected_source_digest and edits (section/path/value records). The output
directory must not exist. It receives source.json, canonical interactive
story.html and receipt.json with exact base/revised digests and non-certification.

Only bounded original narrative, cast and scene presentation text may change.
Quest predicates, source IDs, runtime authority, release status and rights
cannot be edited. The original catalog remains unchanged. Jeeves exposes
studio_author_revision for the same typed, source-leased preview under operator
authorization, but it never writes files on the model's behalf.


To continue a previously exported original revision, pass --revision-source
EXISTING_DIRECTORY alongside --author-revision, --revision-request and a
different new --output directory. The previous source, receipt and playable
HTML are revalidated against their canonical digests before any further edit.
These digests prove consistency, not cryptographic authorship or asset rights.


An exported original revision can also be used with --project PROJECT
--revision-source EXISTING_DIRECTORY --audit-canon or --play-walk, so the
offline replay engine consumes the same source-verified authored content
rather than silently reverting to the registered catalog. Forged, stale,
symlinked or contradictory bundles fail before gameplay.


Revision impact is available as --project PROJECT --revision-impact
--revision-compare-source NEW_DIRECTORY, optionally with --revision-source
OLDER_DIRECTORY. It reports exact changed source paths and digests, playable
HTML differences, and conservative save/replay invalidation; it never
migrates a player's save or certifies the authored ending. Jeeves
studio_author_revision includes the same impact receipt in its typed preview.
