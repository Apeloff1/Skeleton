# Operate the crawler, builder and learning studio

This continuation connects bounded capture, source review, measured Dragon
practice, compiler/artifact workflows and resumable local policy learning under
the existing application, canonical engine and stores. Catalogue entries and
configured budgets remain separate from completed execution evidence.

Start with [the first-install guide](FIRST_INSTALL_AI_AND_CRAWLER.md). Use an
explicitly configured owner account for editor/admin operations. Keep `.env`,
password files and bearer-token files private.

## Installation and readiness

```bash
python scripts/install_app.py --start
python -m skeleton app doctor --live --studio --json
```

The ordinary installer enables empty Dragon schema initialization and selects
the two existing SQLite files in `backend_data`. Startup creates private empty
schemas, with zero knowledge, approvals, lessons or XP. Existing stores keep
their identities. A disappeared live store returns an explicit error.

The studio doctor can query authenticated backend readiness when given
`--auth-token-file /absolute/private/token.txt`. Its local inventory describes
the CLI host; its server report describes the backend. Inspection never launches
a game, compiler, crawler, model or training job.

Native compilation and emulator execution need approved toolchain/core/firmware
identities and the mandatory sandbox. The default Alpine backend cannot execute
arbitrary glibc host binaries. Use an appropriately configured Linux backend for
native work and inspect its actual readiness. Mounting a directory alone does
not establish ABI or sandbox compatibility.

Acquire only explicitly selected tools through the canonical installer:

```bash
python scripts/install_game_desktop_toolchains.py \
  --root /absolute/private/studio-toolchains --tool rgbds --download
python scripts/install_game_desktop_toolchains.py \
  --root /absolute/private/studio-toolchains --tool rgbds --inspect
```

Without `--download`, provisioning uses only pinned cached inputs. RGBDS/cc65
selection does not silently acquire Go or SDL. Source pins, installed hashes
and receipts are checked before atomic publication. Preserve licences and use
the existing emulator installer for approved cores. Game content and firmware
retain their separate admission workflow.

## Capture, inspect and review

In `/crawler`, create a capture with explicit URLs, purpose, rights references,
consent expiry and request/byte/page budgets. Run grants a finite number of
autonomous slices and a deadline. The existing scheduler consumes that intent;
closing a browser never renews it or restores consumed credits.

Pause disables continuation. Resume restores queue eligibility; a subsequent
Run explicitly grants another bounded window. Cancel stops capture/source use.
Erase removes the source snapshot and its downstream eligibility. The exact
owner can still stop/erase after role demotion or consent expiry. New capture
requires current canonical editor/admin permission.

The source library supports incremental source pages, lexical search and
digest-bound text chunks. Offsets are Unicode codepoints. Preserve whole-content
and passage identities when selecting a quotation. Page instructions remain
untrusted external material. Worker status distinguishes an observed local
executor join from an expired remote lease.

Select an exact quotation, annotate a design observation and select its mechanic.
An editor/admin explicitly approves it as a design reference or rejects it,
with rationale and a separate rights attestation. Approval records an immutable
review and canonical note/revision. Confidence stays uncalibrated; the annotation
has research/design-reference rights, with no model-training permission.

Jeeves retrieves admitted annotations through `knowledge.search`. References
retain capture/consent, revision/note and content identities. Decisions cite
host-issued evidence; stale, unknown or withdrawn identities are rejected before
execution and final completion. Legacy consumers without a trusted source
verifier cannot retrieve reserved crawler-reviewed notes.

## Observe Dragon practice

Explicitly run a practice exercise for a supported reference mechanic. Dragon
plays the fixed coded eight-bit reference environment and retains actual
transitions, rewards, source pins and a measured observation. Limits are 512
steps/ten seconds per attempt, sixteen attempts per owner/day, three attempts
per exact request, one live exercise per owner and two globally. Interrupted
attempts retain actual checkpoints; completed replay returns its original receipt.

`knowledge.practice` retrieves a particular completed exercise with the full
stored receipt SHA and current source checks. Compact model context omits raw
traces/images. The observation retains its runtime and trace identities. This
reference exercise awards no XP and makes no claim that the source proposition
was verified or a policy trained. Existing calibrated promotion/ApprovedLesson
gates remain separate.

## Build, preview and export

Save the console project, then preflight its current source and fixed toolchain
plan. Build starts a governed compiler job. A source-generation plan cannot
satisfy a binary requirement.

Preview a successful admitted artifact through its actual registered runtime.
The bounded preview returns producer/input/toolchain/source digests, simulation
receipt, session/snapshot identity and final-frame evidence. It supports
registered NOOP/movement controls without a learned policy. Existing live-play
controls support interactive and AI-controlled play.

Export current source or a verified binary through authenticated downloads.
Tool results identify bytes actually generated or read, without claiming that a
client downloaded them.

Assistant goals can require `edit`, `build`, `preview` and `export`. Completion
checks use current original-owner receipts at the current project head. A model
stop statement cannot satisfy missing requirements. Historical goals without a
checklist retain their existing unverified-stop semantics.
The native checklist is for canonical console editor projects. Attempting it
on another project type returns an explicit admission error before creating a
goal or calling a model.

For an original successor, select `completion_mode: original` and the
`edit`, `simulate`, `review`, `package` and `export` requirements. Start from
an ordinary base project or an existing saved successor. Console editor and
studio-session projects need a separate original project; this workflow does
not convert those source roots. Creation and adoption require the explicit edit
grant. Omitting the mode retains the native and historical behavior.

The planner can synthesize from one or three registered authored profiles,
adopt its completed candidate, inspect and edit the saved world, simulate it,
request a numerical review, build an available desktop target and prepare both
source and package exports. Stage guidance uses actual current-source receipts
and toolchain readiness. Adoption counts as creation; a review does not force
an arbitrary edit. Further refinement uses the same finite goal budget or a
separately authorized goal. A source edit invalidates downstream evidence.

Original completion requires positive committed simulation steps and a real
frame, a current digest-checked review and a current `binary_ready` desktop
package. The simulation measures the source runtime. The desktop package is a
compiled browser-rendered launcher; these checks do not prove that it ran on
the target OS or certify subjective game quality. Both export preparation facts
remain separate from a client download. The limits remain eight model calls,
sixteen actions and four jobs; an unavailable toolchain or exhausted grant can
leave an honestly incomplete goal.

New checklist decisions expose the next prerequisite stage from those receipts,
regardless of model capacity. Export progress reports source and binary
preparation separately. Once one counterpart is verified, the planner receives
only the missing export operation, together with the actual current artifact
identities. The host already waits for a child build before requesting another
decision. Preparing bytes does not verify that the client downloaded them.
Each advance request joins at most one model poll and yields after its durable
operation; already-issued compound actions retain the requested step bound.
Continue using the returned cursor and status until terminal. The model work
keeps its original identity when a poll returns before inference finishes.

New decisions use the selected engine model's declared context capacity. When
needed, the planner supplies the exact goal, current project identities, current
workflow stage and its typed forms in a compact projection. It adds complete
observations only when they fit and records what was omitted. A model that
cannot fit this minimum returns an explicit capacity error. Existing frozen
prompts keep their original identities.
For new decisions, an incomplete required workflow permits only a real granted
operation with `done=false`; the terminal response branch becomes available
after the host verifies the requested facts. Model output still requires owner
validation and can fail without executing a tool.
New decision and follow-up payloads also use the existing tool request forms.
Required editor fields, nonempty edit lists and the observed manifest identity
are constrained before inference. Shared schema definitions keep the full tool
inventory within its existing bound. Owner validation still checks nested game
records, rights and live project identities before any mutation.

## Train, observe and retain lessons

The learning panel exposes actual local Q-learning controls: rate, discount,
exploration/decay/floor, least-visited exploration, n-step backup, imitation
strength, episodes and observed worker capacity. Consented human recordings are
explicit demonstration inputs. Native work binds exact admitted content/core
identities.

Parallel actors execute isolated rollouts and commit batches atomically.
Cancellation drains physical work before capacity is released. A cooperative
deadline with a committed checkpoint is interrupted/resumable. Resume retains
original request, policy, source and teacher authority, with no uncommitted
transitions counted as learned.

The acknowledged job checkpoint owns the committed training trace. Episode
exports are projections of that checkpoint, repaired before a later checkpoint
can replace it or completion can publish. A missing export row cannot roll back
acknowledged learning. An uncertain database acknowledgement remains an explicit
resumable interruption until exact worker-owned readback confirms the commit.
Resume validates the frozen training plan and source identities before updating.
Stopping queued work does not schedule it as a side effect of inspection.

Where the server exposes `cpu_throughput`, selecting it allows training to borrow
idle play slots from the same existing physical credit pool. Active human play
and training still compete for those exact credits. The ordinary CPU profile
keeps its existing allocation.

Studio engine probes, mirror views, shadow scrutiny and multifactor helpers also
hold the existing shared CPU credits while physical computation runs. Request
cancellation drains finite work before releasing those credits. Campaign-bound
results recheck current source and teacher authority before publication.

Evaluation uses disjoint held-out seeds and measured candidate/baseline returns.
Acceptance metadata remains distinct from production promotion. Inspect/export
policy snapshots, evaluation, committed episode evidence and campaign role/lesson
reports. Campaigns retain accepted and rejected experiment lessons for later
bounded proposals. A configured 100,000-round run is a budget; only committed
rounds count as executed.

A candidate that fails its configured return gate remains available for explicit
inspection and export without replacing the default policy. A passing candidate
can become the workspace default only when its evaluated baseline is still the
current default at the same project head. Concurrent work cannot silently replace
a newer selection.

## Compare review observations

Run an original reference review, then select it as the baseline for another
review at the same source head. Paired comparison requires matching environment,
implementation, seed, planned steps, capture interval and controller protocol.
Different frozen policies can be compared under that protocol. Mismatched or
legacy evidence produces an explicit inconclusive comparison.

Reports retain actual Jeeves execution, Dragon numeric/source findings and
adversarial comparability/regression scrutiny. Priorities link actual findings
to evidence and typed remedial proposals. These deterministic roles are labelled
explicitly; task returns and control observations are not subjective game quality.

Authenticated review export returns the exact completed JSON and an
`X-Content-SHA256` header after current source/policy/baseline checks. Offline
operation timing remains separate from display FPS.

Actual session results are recorded in
`machine/ai_studio_enablement_session_evidence_2026-10-15.json`; the subsequent
reliability work and fresh operational receipts are in
`machine/ai_studio_reliability_session_evidence_2026-10-15.json`. The latter
includes a completed seven-call model workflow through real console compilation,
native preview and both exports; three checkpoint resumes through eight native
episodes; source withdrawal enforcement; and a UI chat recovered after reload.
Each observation retains its actual source and package identity. Every-console
compatibility, semantic understanding of arbitrary ROMs, universal native editors
and guaranteed improvement remain outside this continuation's evidence.

## Recorded operational qualification

See [the original creation and playable-learning qualification](STUDIO_CREATION_QUALIFICATION_2026-10-15.md) for executed workflow results, installation observations and the remaining console and model-learning limits.
