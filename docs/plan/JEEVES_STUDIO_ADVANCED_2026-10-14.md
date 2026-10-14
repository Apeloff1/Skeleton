# Advanced Jeeves studio continuation

This continuation implements the user's **More** request against the studio app.
It began at **2026-10-14 06:54:57 UTC**; concurrent implementation owners froze
around **07:39 UTC**, followed by integration, source validation and publication.
The earlier two-hour implementation remains documented in
[JEEVES_STUDIO_IMPROVEMENT_2026-10-14.md](JEEVES_STUDIO_IMPROVEMENT_2026-10-14.md).

This is an implementation candidate, not a declaration that every console,
commercial game, genre, 100,000-round workload or studio-quality target is solved.
No automated tests were created or run, as requested. Actual authoring, compilation,
emulator execution, learning and frontend export workloads were performed.

## Completed build → actual cartridge execution

A completed owned console build now supports readiness inspection, admission,
user/AI playback and training through the existing console-build and live-play
owners. These are executable paths, rather than a binary download alongside an
unrelated design simulation.

The source association preserves the producer's project revision: adding a derived
artifact membership does not increment the project version and immediately
invalidate its own completed build. It does not silently select that artifact as
the default simulation. An explicit `source_id` selects real compiled execution;
the editable design remains the default.

Every admission binds the exact completed producer job, current input epoch,
source tree, target, artifact format, full chunk coverage and SHA, approved core,
registry digest and inherited source obligations. An old producer, withdrawn
source, modified chunk, changed core approval or mismatched target fails explicitly.
Artifact IDs are retained before large receipts are compacted. Historical compiled
outputs remain visible and cannot poison new design/editor/build input bindings.
They are excluded from parsed source inventories used to infer game feel.

| Existing API | Behavior |
| --- | --- |
| `GET /api/game-learning/projects/{project}/build-artifacts/{artifact}/playback` | Current readiness and exact approved execution identity |
| `POST .../{artifact}/admit` | Derived compiled-source admission without revision advance |
| `POST .../{artifact}/play` | Existing real emulator live-play authority, including human input |
| `POST .../{artifact}/train` | Existing bounded learner jobs on the admitted cartridge |
| Existing artifact download | Exact completed bytes and digest |

Actual native libraries and firmware readiness remain those established in the
previous pass: **34 compiled libraries, 29 approved configurations, 46 mapped
hardware targets out of 169**. This continuation connects studio authoring to those
owners; it does not convert catalogue membership into compatibility evidence for
every title. Firmware and renderer blockers remain explicit.

## Scene hierarchy, animation and event editing

`game/editor/graph.json` adds a validated `skeleton.console_scene_graph.v1` document
alongside the existing console document. Its hierarchy, atlas animation, variables,
conditions and rules are consumed by the actual design simulator and persist in
snapshots. They are editable through the same manifest CAS, transaction receipts,
undo and source handoff as other console assets.

The graph supports parent composition, entity bindings, visibility and offsets,
real decoded atlas regions, fixed-tick linear/step animation, input/interval/region/
event triggers, bounded conditions, variables, atomic trades, resource changes,
dialogue, teleport, rewards, win events and existing audio cues. Player movement
remains with its controller. Rule-produced events are consumed on the next tick;
region entry and replay state retain their edge semantics.

Bounds are explicit: 256 nodes, depth32, 128 animations with at most128 keys each,
32 variables, 64 rules with at most8 conditions and16 actions, and512KiB graph JSON.
The learner exposes fourteen base features and the first eighteen sorted graph
variables; the interface marks this as partial observation when additional
variables exist. Native ROM graph mechanics need an explicit source port. Animated
platforms do not automatically carry the player.

The Game Boy native starter now supports an actual **32×32 tile world**, world-space
collision, camera `SCX`/`SCY`, and safe shadow-OAM DMA. An original authored scene
compiled with the fixed RGBDS owner into a **32,768-byte ROM**, SHA256
`30dca61a66f1d9737984c184756bf9a94e1b983c5dcfbcd57c0e45e171d9c56d`.
Gambatte then executed **271 actual frames** with captured scrolling PNG evidence.
NES binding remains a physical viewport. These kernels do not claim full native
farming, audio, advanced scrolling or all-genre source generation.

## Measured Dragon sequence reviews

The new review owner executes a bounded immutable project runtime, rather than
accepting arbitrary uploaded screenshots as execution evidence. It records actual
controller actions, frame digests and thumbnails, decoded raster statistics,
adjacent-frame differences, temporal feature transitions, measured step/render
wall times and byte budgets. Findings point to their actual frames and trace.

`POST /api/game-learning/projects/{project}/review` uses the existing workspace
`review` job. Review-specific reads revalidate the completed issuer, exact result
hash, project/source/policy identity and teacher/source rights. The worker uses the
existing slots, heartbeat, cancellation and publication fences; quota is reserved
before execution. Bounds include512 steps,25 frames,60 runtime seconds and2MiB
results.

These are numerical inspection aids. They do not assert subjective aesthetics,
OCR/HUD comprehension, accessibility certification, display refresh, isolated
memory, native presentation FPS or human mastery. Repeated images during observed
motion are candidates for scrutiny, not proven stutter. Campaigns inspect their
existing first/final frames; that does not measure their intermediate animation.

## Remembered multiobjective improvement

The campaign snapshot is now **v2**, with explicit incompatibility rather than
implicit migration of old checkpoint semantics. It persists deterministic UCB1
proposal selection over supported numeric mechanics, economy, entity, layout and
fidelity arms, plus exact-parent policy continuation. Rejected arms still update
its proposal memory, while accepted champions require actual evidence.

Each evaluation uses **three ordinary and three adversarial seeds by default**,
configurable up to eight per partition. Candidate and champion are compared on
paired held-out trajectories. Objective vectors include actual return,
completion, survival, binned state coverage and action entropy; death,
per-seed regression, latency and other declared constraints remain explicit.
The cumulative slice bound includes all training and all four paired evaluation
trajectories per seed, with a131,072-transition ceiling.

Counterexamples retain actual seed/trace evidence. Later training can execute
those seeds as labelled new curriculum episodes; it does not relabel old held-out
results as measurements of a changed source. Policy continuation forks the exact
admitted parent snapshot and reports the actual new update delta. Full lesson
history remains in bounded, indexed, scoped evidence pages; recent runtime memory
and seed memory have fixed bounds.

Backend recovery now handles restart/orphan states, exact frozen pulse requests,
reusable worker attempts and final-round quiescence. It archives immutable attempt
receipts before resetting the worker handle. Five consecutive no-progress failed
epochs trigger a bounded backoff and explicit pause, rather than an endless rapid
retry. The existing scheduler performs an immediate startup sweep and then a
30-second sweep of at most32 explicitly authorized, unexpired campaigns. It does
not introduce another service or schedule ungranted campaigns.

Champion handoff/export/adoption is source-only and exact: an issued promoted
candidate/policy, regenerated complete source, current CAS and original source,
teacher and policy-ancestor obligations. Original and inherited teacher references
are normalized. Recursive policy/source lineage is bounded and deduplicated, and
future withdrawal reaches descendants. Exact prepared editor recovery is allowed
only for its owned committed/pending operation identity; Dragon writer guards are
retained without nested SQLite re-entry.

## Jeeves uses the actual application

`/api/game-studio-agent` adds owner-scoped project goals, bounded advances and
pause/resume/cancel. The assistant uses **canonical EngineChat → EngineText** for
model planning, followed by strict application request models and existing studio
owners. It introduces no provider SDK, raw model networking, credential surface,
shadow database or autonomous service. A missing model service produces an
explicit `studio_planner_unavailable` result.

Plan mode records an actual model proposal. Run mode dispatches granted commands;
shared-file edits require the explicit edit grant. The goal exposes exact schema
and editor operation discovery, graph record examples, bounded source pages,
section/record/array inspection and current artifact readiness. A planner cannot
choose another actor, project, shell, compiler path, core library, teacher consent
or source-rights flag.

Goal intent and receipts use existing `game_learning_revisions` journals. Before
model execution, the exact prompt and canonical idempotency key are persisted.
Before action dispatch, the exact typed command/key is persisted. Model terminal
lineage, invalid-response digests, action outputs and command identities are
recorded. A crashed own edit recovers only from the exact issued editor request,
committed revision membership, expected next version and complete source digest.
Concurrent unrelated edits block reuse.

All historical source/teacher/policy evidence is reauthorized before it re-enters
model context. External sources retain their exact origin version/epoch semantics.
Historical policy admission skips only current tree equality; source, content,
core, producer, ancestor and consent checks remain. Large feedback retains actual
artifact, policy, play, session and metric identities instead of losing the
execution join when its source text or trace is compacted.

Bounds include16 action steps,8 model calls,4 queued jobs/AI plays, a one-hour
maximum grant,90-second worker leases,8MiB journals,256KiB prompts and128KiB
decisions. There are at most64 goals per project,128 advance receipts and64 control
receipts per goal; completed keys are not silently evicted. Each AI cartridge
play forces an admitted policy, AI controller and at most256 frames. Its actual
terminal status gates the next action. Interrupted jobs/play expose their real
recoverable state. GET polling does not consume advance budget.

Already-issued work retains its own job/play controls. Goal pause/cancel prevents
new actions at the current issued operation boundary. Agent-created campaigns
disable automatic continuation; separate campaign authorization is explicit.

## Product UI and export

The existing game-learning studio now includes cohesive learning subtabs,
compiled-ROM readiness/play/training, shared scene/timeline/rule editing, scoped
assistant Plan/Run controls, concurrent pause/cancel, actual review thumbnails and
findings, multiobjective/curriculum controls, authorization renewal, champion
source handoff and paged lessons. Auth/account changes and stale request callbacks
are fenced. The assistant client allows180 seconds for a bounded advance and
retains exact retry keys. Frames and job completion are actual owner projections.

The final production Expo web export contains **186 HTML routes,292 files and
33,373,834 bytes**. Its actual generated bundle contains all new workflows.
Foreign-OS execution/signing and all-ROM compatibility were not asserted.

## Productive workloads and evidence

| Workload | Actual retained evidence |
| --- | --- |
| Graph authoring/reopen |120 original simulator ticks, real hierarchy/atlas/rules/trade changes, replayed next-tick and region-edge state |
| Native scrolling |32KiB fixed RGBDS cartridge,271 Gambatte frames, actual PNGs |
| Successor campaign |6 rounds,8,064 steps,1,152 candidate Q updates,384 parent updates,12 retained counterexamples,24 lessons; midpoint reopen |
| Reference curriculum |3 rounds,2,688 steps,384 candidate updates,128 parent updates;2 actual counterexample-seed training episodes; checkpoint reopen |
| Temporal review |16 actual steps,9 rendered frames,50,551-byte inspectable report |
| API schema generation |27 actual application operation schemas;15 OpenAPI paths,11 request schemas |
| Frontend production |186 routes/292 files, successful Expo export |

The combined new campaign work is **9 rounds,10,752 steps,1,536 candidate updates
and512 parent updates**. Every candidate was rejected and its champion retained.
No improvement, completed100,000-round campaign, subjective studio quality or
commercial-game mastery was fabricated.

Evidence directories in this session workspace are
`/workspace/scratch/console-editor-graph-authoring`,
`/workspace/scratch/console-editor-scrolling-authoring`,
`/workspace/scratch/studio-multiobjective-workload`,
`/workspace/scratch/studio-counterexample-workload`,
`/workspace/scratch/studio-actual-review-final`, and
`/workspace/scratch/jeeves-studio-app-web-advanced-final`.
Whole provider ownership validation passed; final changed-source validation,
architecture/construction/capability checks, enterprise source validators,
canonical mirror checks, Ruff/Black/Python compilation, TypeScript, ESLint and
production export are recorded separately. The final deterministic archive is 9,207,333 bytes, SHA256 `1694ecba3e59f8f43d6dddf768171f2ec7705300ba8f4dca45bd708e96e0b636`. These are source/build checks,
not automated tests or authenticated API end-to-end evidence.

Hosted model execution, an authenticated production Mongo/API workflow,
100,000-round endurance, every-console emulation and subjective quality superiority
remain unverified. They require configured services, original assets/ROMs,
compatible cores/firmware and sustained real workloads. This report does not
promote a masterplan, enterprise claim, closure marker or production deployment.
