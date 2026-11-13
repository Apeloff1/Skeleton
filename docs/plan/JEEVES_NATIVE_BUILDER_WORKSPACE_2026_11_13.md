# Jeeves native game-builder workspace

Implementation candidate on top of the live Forge prototypes and local-model
quality diagnostic drafts. This increment composes the existing local Jeeves
HTTP workspace, admitted model backend, inference lease, SQLite file, Forge
compiler and Godot verification. It creates no network service, provider, model,
authentication realm or conversation authority.

## L00 — Product outcome and scope

A creator selects a small shooter, platformer or roguelike, describes a game,
reviews concrete gameplay choices and explicitly starts a build. The workspace
shows durable progress and the resulting design, native verification and source
archive. Downloaded projects open in Godot. This is a source-project prototype;
creative quality, human fun, device performance and store distribution require
separate acceptance.

## L01 — Canonical ownership

`skeleton/app/offline_game_builder.py` owns local application composition and
bounded job persistence. `offline_http.py` projects that operation through the
existing authenticated numeric-loopback server; `offline_web.py` renders it.
`skeleton/forge/game_builder.py` retains source compilation authority and the
existing local inference plane retains model execution. The operator CLI uses
the same application operation. The model proposes bounded data, never code,
paths, providers, tools or a changed genre.

## L02 — Request and interface

The strict submission has only `request_id` and `brief`. The brief is at most
4,000 UTF-8 bytes. Creator choices use the existing explicit gameplay labels;
conflicting labels are refused rather than silently overwritten. The route set:

- `POST /v1/game-builds`: admit an immutable request or replay its existing job.
- `GET /v1/game-builds`: scoped history, current availability and fixed limits.
- `GET /v1/game-builds/{request_id}`: durable job and terminal result.
- `GET /v1/game-builds/{request_id}/archive`: verified binary source ZIP.

No request accepts a model manifest, destination, command, engine binary or
filesystem path. Existing bearer, origin, Host, body-size and JSON controls apply.
Tokens remain in tab memory, outside URLs and persisted browser storage.

## L03 — State and consistency

The additive `offline_game_builds` table resides in the existing operator-selected
workspace SQLite file. Jobs are scoped to the admitted model/tokenizer identity;
request IDs bind immutable request digests. Reuse with different input conflicts.
A file-wide active-slot constraint and a distinct OS work lease prevent competing
processes from starting overlapping builds. The existing inference lease covers
actual model execution and physical drain; work and inference leases are distinct.

Queued, planning, building, verifying and publishing state are durable. Terminal
results are fenced. Thread handles and progress observers are derived execution
state; a missing observer is never evidence that a model should run again.

## L04 — Model and compiler boundary

A complete accepted structured design is required. The existing strict parser
and guard reject unknown fields, malformed values and changes to explicit user
constraints. At most one bounded repair is allowed. The deterministic compiler
retains the committed genre, scope and engine. There is no hosted fallback or
silent substitution of a compiler-only result for an accepted model proposal.
Schema compliance alone does not establish useful design or code quality.

## L05 — Native acceptance

The trusted compiler emits maintained Godot source and an input replay. A
successful workspace archive requires actual native import and the ordinary
movement/action, win, pause and restart journey. Content arithmetic, boot and
input evidence are distinct fields. Missing Godot, invalid design, deadline or
failed native proof cannot create a qualified downloadable result. Arbitrary
model-written source is never executed.

## L06 — Artifact publication and recovery

Projects are built in private staging. ZIP entries come from the canonical source
file mapping, excluding engine caches, model weights, credentials and unrelated
filesystem files. Paths, entry count and total bytes are bounded. Expected ZIP
and receipt identities are persisted before atomic create-only publication.
A terminal result follows publication. Recovery may recognize a previously
published bundle only after exact scope, size, hash and receipt verification.

A startup process must acquire the work lease before reconciling orphaned work;
it cannot mark a live peer's job failed. Interrupted unpublished work terminates
without automatically repeating model inference. Missing, changed, oversized or
unsafe archives are withheld. Artifacts are preserved for diagnosis; another
request never overwrites an existing bundle.

## L07 — Budgets and economics

The browser operation uses fixed server bounds: 256 output tokens, 90 seconds
for planning, 180 seconds total and a 16 MiB archive ceiling. One active build is
admitted per workspace file. The local deployment can impose stricter context,
resource and runtime limits. History admission is bounded; there is no unbounded
background worker fan-out, remote spend or automatic model acquisition.

## L08 — End-user behavior and accessibility

The builder shares navigation and connection state with chat. Starter choices,
labels, progress, errors and download controls are keyboard-accessible. Starting
a build captures the exact submitted brief; subsequent edits do not mutate it.
The archive describes controls and how to open `project.godot` in Godot.

Locking the workspace stops observation/download activity and clears private UI
state. It does not claim that a disconnected tab cancelled a durable build.
Reconnect lists the original job and allows explicit observation and download;
refreshing the page never automatically submits another model request.

## L09 — Observability

Public status contains stable stages, request and archive fingerprints, accepted
proposal evidence and native acceptance. It excludes host paths, subprocess
commands, raw stderr and bearer credentials. Errors use safe public classes.
Raw diagnostic artifacts belong in operator-private evidence directories, not in
browser messages or committed model configurations.

## L10 — Verification

Verify the shared operation and the real SQLite/HTTP boundary separately from
model quality. Failure tests cover duplicate identity, concurrent peers,
interrupted work, verified publication recovery, archive tampering and scoped
reads. Browser acceptance must use the actual local model and Godot to qualify
the end-user build/download journey; a patched counting fixture qualifies only
request/state plumbing. Record source hashes and archive hashes with evidence.

The earlier fixed public diagnostic retained 96 real responses. Structured
0.6B scored 15/24 strict task passes; cited Godot notes also scored 15/24, with a
paired improvement and regression. The separate 1.5B coding candidate scored
13/24. Neither the UI integration nor those diagnostic scores promote a model
or establish generalization or competitor superiority.

## L11 — Backup, restore and deployment

Start the existing local server with an explicit admitted GGUF deployment,
private database and new token file. Install a supported Godot binary before
building; list/status must explain unavailability. Preserve the existing database
through SQLite's consistent backup mechanism, together with the exact referenced
immutable archive set and original private permissions. Restore and verify the
SQLite authority before exposing artifacts. A documented protocol is not a
completed backup/restore or device qualification.

For this prepared workspace, select a new token filename and run from the
repository root (the database parent must already exist and be private):

```sh
.venv/bin/python -m skeleton.app.offline_http \
  --gguf-deployment /workspace/jeeves-local-model/jeeves.json \
  --database /workspace/jeeves-workspace-runtime/jeeves.sqlite3 \
  --token-file /workspace/jeeves-workspace-runtime/builder-access-token.txt \
  --port 8766 --open-browser
```

The process prints the loopback address and private token-file location. Read
the token locally and paste it into the connection panel. Choose **Game builder**,
review a small brief, then explicitly start the build. After completion, download
and extract the ZIP, read `PLAY.md`, and import `project.godot` in Godot. A token
filename that already exists is refused; never delete or overwrite a live token
file to make startup succeed.

## L12 — Failure and rollback

A rejected request leaves existing jobs and chat receipts intact. Loss of the
model or Godot blocks new work while verified historical results remain readable.
Closing the application drains its bounded game worker before closing dependent
stores. After interruption, explicit new work requires a new request identity;
unknown-result inference is not silently repeated.

The interactive verifier inherits work-lease custody on POSIX. The earlier
canonical compiler import/boot subprocess retains its existing lifecycle: after
an abrupt supervisor death, a native child may finish in private scratch. It
cannot publish this operation's final bundle. Exclusive resource ownership of
every orphaned engine process, Windows power-loss durability and device-level
crash recovery remain unqualified.

Rollback removes the optional route/UI adapter and retains database records and
archives. The existing chat and operator interfaces remain the owners of their
state. Never remove a persistent OS lock marker while another process might
hold its inode. No production merge or publication is part of this prototype.

## L13 — Evidence and qualification

Record actual test, browser and native results on the reviewed source revision.
Source checks, fixture plumbing, genuine model generation, native input, rendered
play, hardware performance and human acceptance remain separate observations.
Only a blinded, controlled comparison of equivalent end-user journeys can
support a statement that this builder beats another product.
