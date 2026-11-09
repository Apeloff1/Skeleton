# Dragon resource-aware cognition extension — 10 October 2026

Status: implemented library composition and mounted chat waiting toy; production-wide rollout remains open. This extends draft PR #3605. No enterprise/SOTA qualification or entire-volume completion is claimed.

## Ownership and application placement

- `skeleton/ai/webcrawler/dragon_reasoning_matrix.py`: bounded four-state evidence logic, exception policies, and evidence-gap search queries. Missing/expired facts remain unknown. Contradictions remain visible. WHEN/HOW/WHY/WHAT/WHERE/THIS/THAT/THERE are explicit typed bindings, not an unvalidated natural-language resolver.
- `dragon_microknowledge.py`: a rebuildable projection of `DragonKnowledgeGraph`, using covering posting/facet indexes. Canonical concept text is not duplicated. Query-time principal, facet, expiry and content-digest checks precede context use.
- `dragon_resource_session.py`: a composition adapter over the existing product scheduler and canonical `skeleton/kernel/global_resource_scheduler.py` physical-capacity owner. No new runtime/service/provider owner. A shared injected global scheduler charges CPU, memory, GPU, I/O and provider tokens across sessions; planning without it never grants execution authority. Hardware samples expire after five seconds; all time inputs use the caller's same clock domain.
- `dragon_companion_runtime.DragonCognitionSession`: combines evidence eligibility, hardware/resource policy, retrieval and canonical scheduler dispatch. It returns explicit checkpoint IDs; only executing workers can acknowledge stopped resources.
- `dragon_idle_service.plan_idle_video_research`: optional hardware admission defers low-battery, thermally limited, busy or stale-telemetry background proposals before history lookup. Existing consent checks still precede access. Legacy callers without telemetry retain their existing behavior; this is not yet a global hardware enforcement rollout.
- `dragon_capability_gap_matrix.py`: ranks independently supplied, attributable, unexpired coverage deficits across genre/era/engine/story/time-setting and other game factors. These are deterministic priority estimates, not a newly deployed adversarial model or empirical predictions.
- `dragon_conversation_micro_logs.py`: a derived ten-step conversation-window projection. The existing canonical conversation repository remains authoritative. Retention consent and principal match are required; training eligibility requires a separate explicit flag. No feature starts training.
- `frontend/features/Jeeves/companion/dragonMagicEightBall.ts`: 24 software phrases, no model/network/timer/storage. Mounted in `DragonCompanionPanel` through `ChatWorkspace`'s existing active request identity. The labelled waiting bubble disappears with the request. It never enters the transcript as the model's answer. Includes playful yes/no/maybe phrases explicitly labelled as toy output; the real answer is still pending. These are not factual verdicts.

## Microknowledge design

A chunk is one bounded canonical concept (at most 4096 UTF-8 bytes), an evidence reference, expiry and domain-specific facets. Retrieval coefficients are quantized integers 0–255; they are lexical relevance weights, not neural parameters, confidence probabilities or proof of truth. The projection stores indexes and digests only. The source statement remains at its existing owner.

Supported facets: genre, era, engine, platform, story, timesetting, mechanic, rendering, input, audio and accessibility. Hard factor matching occurs before candidate LIMIT. This prevents a large modern-engine collection from hiding the applicable historical match. Unknown factor coverage is reported explicitly. Selected content is labelled untrusted reference material and cannot supply system policy or release authority.

Per query: at most 16 terms, 256 candidates, 64 KiB serialized context, 4 KiB serialized chunk and 200,000 SQLite VM instructions. Per owner: 10,000 indexed concepts. A high-frequency query that exceeds its instruction budget fails with a narrow-query diagnostic. No whole-graph scan or embedding model is necessary. Deletion removes postings and facets. Drift/corruption requires rebuild from the canonical graph, not repair of authoritative content.

SQLite connections are worker-owned and not concurrently shared during bounded retrieval (the VM progress callback is connection scoped). Capacity decisions take the SQLite writer lock before checking counts. There is no global process cache growing with every user.

## Hardware and time policy

User work takes priority. Background order: autonomous actions, idle actions, training, acquisition/distillation. Hardware generation or game release year does not grant resources: a phone may retrieve modern technical knowledge, while an overloaded desktop must defer. Scope follows measured headroom and proven compiler/runtime capability.

Foreground memory admission uses at most half currently available memory, capped at 512 MiB. Background uses at most one eighth. Below an 8 MiB work envelope, pressure >=95%, thermal limitation or stale telemetry: defer. Below 20% battery while unplugged: no new background work. Background pressure must be below 50%. CPU budgets remain 1–4 scheduler units, not a promise of OS core pinning.

When foreground arrives, checkpointable background tasks are asked to yield. All background reservations remain charged until `stopped(task_id)` acknowledgement. Foreground cannot begin while a background worker remains active, including a noncheckpointable worker. This prevents the common unsafe shortcut of assuming a cancellation request instantly frees RAM. Missing acknowledgements require existing worker supervision; this adapter never kills another process.

High effort is advisory only: foreground, pressure below 25%, and at least a 128 MiB admitted memory envelope. Other admitted work uses low effort. Global vector reservations include explicit declared provider tokens, GPU milliseconds and I/O tokens. Model routing, monetary cost, actual KV-cache allocations, privacy and execution remain controlled by canonical provider/accounting owners. Local planning reports `execution_authorized=false`; callers must require a global grant, not merely foreground readiness. The system must re-sample before every chunk/tool/model launch; an initial admission is not permission to ignore future thermal or battery changes.

Time permits short resumable chunks, not unlimited energy or spend. There is no infinite worker loop or provider call in these modules. Android/iOS background lifetime and battery restrictions still require native adapters. Official guidance: https://developer.android.com/develop/background-work ; https://docs.python.org/3/library/sqlite3.html ; https://www.sqlite.org/queryplanner.html .

## Conversation microcosm

Exactly ten contiguous, committed canonical message steps on the active branch create one immutable checkpoint. The projection contains indexed game-topic bulletpoints and message IDs, not raw transcript text or hidden reasoning. Arbitrary chat content cannot become trusted public knowledge. New hypotheses must pass the existing acquisition/provenance/human-review gates.

Context recall reads only the current authorized tenant/owner/thread/branch, at most ten checkpoints and unexpired rows with digest verification. A restart test reopens a real on-disk SQLite database. Explicit thread deletion removes the projection/index; expiry removes both. The production conversation deletion/retention and context-compiler integrations must invoke these lifecycle adapters before rollout. This module does not silently add a second authoritative hard-drive transcript.

Adversarial coverage input is distinct from conversation observations. The gap matrix requires expected/passed check counts, a review reference, expiry and importance. It ranks missing coverage rather than pretending repeated conversation interest is competence. Deployment must bind these inputs to the canonical independently verified review receipt; the dataclass alone is not receipt authentication.

## L00–L13 evidence and operational boundaries

| Level | Implementation / remaining gate |
|---|---|
| L00 | Existing crawler, product scheduler, canonical graph/conversation and frontend owners |
| L01 | Pure modules; no new service/provider SDK or worker authority |
| L02 | Bounded immutable dataclasses; explicit unknown/conflict and typed factor vocabulary |
| L03 | Authorization/consent before retrieval/checkpoint; evidence before dispatch |
| L04 | Reserved resources, checkpoint request, stop acknowledgement, foreground admission |
| L05 | Derived SQLite tables; canonical graph/conversation remain authority; restart/idempotency tests |
| L06 | Tenant/owner/thread/branch isolation; untrusted context label; separate training consent |
| L07 | Missing/stale evidence, pressure, thermal, battery, invalid facts, corruption and retry policies |
| L08 | Explicit reasons, bytes/candidates/digests, gap evidence references; no raw transcript telemetry |
| L09 | Bounded memory/CPU/context/query VM work; reproducible local benchmark, no device superiority claim |
| L10 | Resource, logic, scope, expiry, corruption, restart, composition and software-toy tests |
| L11 | Opt-in cognition/telemetry adapters; additive projection schema; rollback disables adapters and rebuilds projections |
| L12 | Worker supplies trusted current telemetry and stop acknowledgements; existing runtime supervision handles stalled workers |
| L13 | Full platform hardware telemetry, all worker integration, native background service, model-backed review and low-end end-to-end qualification remain open |

The application-wide hardware guarantee requested by the user is NOT yet complete. The phone-to-original-game and Windows large-project journeys need consumer hardware acceptance, native engine execution and actual provider/resource integration. This extension supplies the bounded composition and mounted waiting behavior rather than falsely claiming those journeys work end to end.

## Validation

Focused tests: `tests/test_ai_dragon_resource_cognition.py` (35 passed). Full Dragon suite and full frontend TypeScript are run separately. The new waiting toy checks run in the existing `test-dragon-wisdom.cjs` CI step. The original mandatory implementation-notes validator has the previously reproduced baseline stale-summary failure; it must not be bypassed or masked.

Reproduce the local retrieval comparison with `python scripts/benchmark_dragon_microknowledge.py`. It uses 1000 synthetic canonical concepts, 40 interleaved queries per method, matching top-20 IDs and identical lexical query input. Results are container diagnostics, not phone/Windows benchmarks or production p99 certification. The existing full-scan path includes its canonical graph audit; the new path validates each selected concept digest and does not replace that whole-graph integrity function.

Local benchmark result (Linux x86_64, Python 3.12.14, SQLite 3.53.1): full scan p50/p95/p99 5.341/5.801/6.029 ms; micro index 1.306/1.581/1.680 ms. These are the specific observed synthetic run, not universal speed guarantees.

A concurrent admission regression checks that eight requests never exceed two admitted session CPU units. Cross-tenant sessions sharing the canonical global ledger cannot overbook its CPU/provider-token budget. Resource decisions remain advisory if the global ledger is not supplied.

The canonical global-scheduler regression suite reports 12 passed and one fairness/aging test failed. The identical failure was reproduced in untouched baseline 79fe3870. This extension does not rewrite that independent scheduler policy. Product/global priority conventions differ and the adapter explicitly translates user priority to global 0; a regression verifies it.

State topology explicitly registers the consented conversation projection as derived and production binding pending. The global resource contract records the Dragon adapter and its focused acceptance suite. Both topology and global resource contract validators pass.

## Reviewed-library refresh increment

The existing `ReviewedKnowledgeStore.plan_recrawl` now derives a bounded,
deterministic refresh plan from one integrity-verified owner snapshot. No new
database, service, provider, or state owner is introduced. This closes the local
review-gap planning step for the Almanakk concept; Wiki/Hoag dual approval,
authenticated crawler dispatch, and permanent-memory promotion remain open.

Run the existing operator CLI with `plan-recrawl --owner STUDIO --as-of
2026-10-10T12:00:00Z`, after its required `--store` and
`--trusted-local-operator` arguments. Optional controls include
`--max-age-seconds`, `--minimum-independent-groups`,
`--minimum-confidence-ppm`, `--scope`, and `--limit`.

The projection reports future timestamps, stale observations, conflicting
mechanic evidence, uncertainty, low confidence and independent-support deficits.
Future timestamps rank first, then contradictions, then stale sources, then
other review gaps; older observations and stable source IDs break ties.
It examines all bounded current sources before limiting output, and reports
deferred work and reason counts. Retractions and out-of-scope sources are
excluded. Only fresh, sufficiently confident supporting observations contribute
independent dependence groups; repeated revisions and copied publishers do not
increase that count. Group labels remain externally reviewed metadata, not a
new empirical independence detector. Mechanic-level conflicts are conservative
triage signals: a reviewer must resolve different contexts and applicability.

Each request binds its source-body digest and expected revision parent. The
existing transactional import rejects stale parents and preserves the revision
chain. Plans include their evaluation clock, policy, owner snapshot and content
digest. Digests detect identity changes; they are not authentication. The
embedding runtime must replan before dispatch, authenticate actors, enforce
crawler URL/permission/resource policy, and require fresh independent review
before importing results. Citation URLs are not network permission. The
projection explicitly grants neither execution nor memory promotion.

L00–L03 retain canonical library ownership and trusted-operator admission.
L04–L07 use read-only snapshot projection and existing optimistic revision
imports, tenant filters and corruption rejection. L08 reports bounded counts
without raw source bodies. L09 is bounded by existing owner revision/claim
quotas and output limits; this is an O(current claims) local planning pass,
not consumer-device performance qualification. L10 covers restart, timestamp
boundary, conflict-before-limit, duplicate provenance, scope/retraction,
stale-parent rejection, corruption and real CLI output. L11–L12 need no schema
migration: rollback removes the command/consumer; canonical revisions remain.
L13 remains open for authenticated end-to-end crawl/review/promotion acceptance.

Validation: `python -m pytest tests/test_game_builder_reviewed_knowledge.py -q`
passed 31 tests and 11 subtests. Sign-off: Codex, 2026-10-10, limited to this
local planning implementation and its focused validation; no volume closure.

## Live telemetry and synchronous chunk execution increment

The canonical HardwareProbe now marks live memory measurements explicitly.
Linux MemAvailable (clamped by a finite root cgroup v2 limit), Windows
GlobalMemoryStatusEx and macOS free-page readings qualify; assumed fallback
memory does not. Windows power status distinguishes a missing battery from
unknown telemetry. Unknown battery readings conservatively block acquisition.
Nested cgroup limits, device qualification and macOS battery telemetry remain
open; this is not an application-wide hardware certification.

DragonLiveHardware adapts this existing owner. DragonChunkExecutor requires an
injected shared global scheduler, explicit authority and consent, and fresh
hardware admission before each synchronous chunk. It checks declared cumulative
token, tool, artifact and retry limits before callbacks; rejects observed usage
above the declaration; and releases grants only after a callback returns or
raises. Foreground arrival is reference-counted, and cooperative checkpoints
also observe canonical global revocation. There are no detached worker threads
or automatic retries. Native/provider calls must enforce their own timeouts.
The injected governor must be exclusive to this executor or externally serialized;
its existing accounting object is not a cross-process resource ledger.

This is an execution adapter with real callback acceptance tests, not yet a
production conversation/scheduler hook. No new provider transport, database,
authority owner or retention policy is introduced. Rollback removes these
optional adapters; existing canonical stores remain intact. Admission failure
performs no callback and consumes no declared usage. A callback that exceeds
its own declaration is rejected after observation; the runtime cannot undo work
already performed by defective trusted code.

## Guarded practice integration

The canonical practice controller exposes pulse_guarded for trusted schedulers.
It binds an injected executor to the authenticated opaque owner, admits one
finite tick through the shared ledger, and rechecks telemetry, foreground yield,
expiry and subscription revision between every artifact. Consent remains in
canonical practice subscriptions and separately approved lessons. A new revision
counter distinguishes deliberate stop/replacement from automatic exhaustion of
the final tick. Existing rows migrate with revision zero without deleting data.

The Academy POST /api/dragon-academy/practice/pulse endpoint uses that controller.
Its executor factory comes only from trusted application state:
dragon_practice_executor_factory(owner). Missing or mismatched configuration
returns 503. The factory must return the owner's serialized executor using the
application's shared global scheduler and retained cumulative governor. It must
not create an independent capacity ledger or reset budgets on every request.
No request parameter can set the owner, capacity, consent or runtime factory.
The existing explicit generation endpoints remain compatibility paths; they
are not covered by an application-wide resource guarantee in this increment.
No production bootstrap currently installs this factory automatically.

Deferral consumes no tick. Once a tick starts, partial completion consumes its
reserved tick and cooldown: restoring it could duplicate committed artifacts.
Each completed attempt is conservatively charged its maximum artifact policy
rather than claiming an exact disk-write measurement. Native project metadata
and sources are now checked against that same byte bound before commit. SQLite
and source generation remain synchronous and bounded by existing quotas; this
path does not compile native projects, invoke models or install a timer.
Checkpoint references point to existing practice records, not a separate store.

L00–L03 preserve practice, auth and resource owners. L04–L07 cover admission,
transactional tick reservation, shared grants and checkpoint revocation. L08–L09
expose defer reasons and bounded accounting. L10 tests real HTML/native source
creation, initial heat/budget/foreground/missing-ledger deferral, interruption
between artifacts, final-tick revocation and oversize rollback. L11 preserves
existing rows during additive migration; L12 rollback removes the consumer and
leaves practice records readable. L13 remains pending production factory wiring,
all-generation-path adoption and consumer hardware qualification.

Sign-off: Codex, 2026-10-10, implementation and local acceptance scope only.
No complete volume or all-engine capability claim is made.
