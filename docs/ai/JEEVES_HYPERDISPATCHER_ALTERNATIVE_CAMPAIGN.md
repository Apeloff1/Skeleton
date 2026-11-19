# Alternative dispatcher adoption — 36 targets

Independent source implementations. P means partial source implementation only; no deployment or measured competitive advantage. Existing canonical runtime, quota, persistence and executor owners remain authoritative. This register is separate from the 72-target primary campaign.

## Research verified against project documentation

- Orleans placement and activation collection: https://learn.microsoft.com/en-us/dotnet/orleans/grains/grain-placement ; https://learn.microsoft.com/en-us/dotnet/orleans/host/configuration-guide/activation-collection
- Pekko passivation and sharding: https://pekko.apache.org/docs/pekko/current/typed/cluster-sharding.html
- Inngest flow control: https://www.inngest.com/docs/durable-execution/flow-control
- Trigger.dev multiple concurrency limits: https://trigger.dev/changelog/multiple-concurrency-limits
- DBOS queues: https://docs.dbos.dev/architecture
- River transactional uniqueness: https://github.com/riverqueue/river
- YuniKorn hierarchy: https://yunikorn.apache.org/docs/get_started/core_features/
- Flux allocation hierarchy: https://flux-framework.readthedocs.io/en/latest/tables/comparison-table.html
- Parsl and TaskVine executors: https://parsl.readthedocs.io/en/stable/userguide/configuration/executors/index.html
- Knative zero scaling: https://knative.dev/docs/serving/autoscaling/scale-to-zero/
- KEDA polling/cooldown: https://keda.sh/docs/2.21/reference/scaledobject-spec/

Further research queue (not yet verified): Restate, Oban, pg-boss, Faktory, Asynq, Sidekiq, HPX, StarPU, PaRSEC, Legion, Charm++, oneTBB, RADICAL-Pilot, Balsam, OpenPBS, Taskflow, OpenFaaS, Apache Pulsar. Their names in the inventory indicate research leads, not verified feature claims.

## Adoption inventory

| ID | Target | Inspiration | Source status |
|---|---|---|---|
| A01 | Overlapping concurrency ceilings | Trigger.dev / Inngest | P |
| A02 | Aggregate global quota | Trigger.dev / YuniKorn | P |
| A03 | Shared dependency or service quota | Inngest | P |
| A04 | Atomic multi-ceiling transitions | Trigger.dev | P |
| A05 | Policy-preserving restore accounting | DBOS / River | P |
| A06 | Keyed singleton ownership | Inngest / Restate | P |
| A07 | Quiet-window debounce | Inngest | P |
| A08 | Maximum-wait coalescing | Inngest | P |
| A09 | Rate-shaped dequeue | DBOS | P |
| A10 | Non-discarding throttle | Inngest | P |
| A11 | Event correlation wakeup | Restate / Inngest | P |
| A12 | Durable timers and waits | Restate / DBOS | P |
| A13 | Atomic outcome plus enqueue | River | P |
| A14 | Transactional unique job identity | River / Oban | P |
| A15 | Versioned activation identity | Orleans | P |
| A16 | Idle actor passivation | Pekko / Orleans | P |
| A17 | Memory-sensitive passivation | Orleans | P |
| A18 | Communication affinity graph | Orleans | P |
| A19 | Bounded migration rounds | Orleans | P |
| A20 | Activation balance and anti-thrash | Orleans | P |
| A21 | Scale-to-zero safety | Knative | P |
| A22 | Cooldown and warm retention | KEDA / Knative | P |
| A23 | Stale scaler metric hold | KEDA | P |
| A24 | Service-rate-based scale demand | KEDA / Parsl | P |
| A25 | Uncertain execution capacity floor | Jeeves extension | P |
| A26 | Hierarchical allocation subleases | Flux / Parsl | P |
| A27 | Nested allocation reclamation | Flux | P |
| A28 | Data-affinity task scheduling | TaskVine / StarPU | P |
| A29 | Shared artifact transfer amortization | TaskVine | P |
| A30 | Versioned environment reuse | TaskVine | P |
| A31 | Data-ready execution barriers | StarPU / PaRSEC | P |
| A32 | Compute-transfer overlap planning | StarPU / Legion | P |
| A33 | Weighted resident shard split | Pekko / Orleans | P |
| A34 | Bounded membership migration | Pekko | P |
| A35 | Measured dispatch policy comparison | HPX / Taskflow | P |
| A36 | End-to-end mixed-workload qualification | All alternatives | P |

## Wave A1: overlapping quota ceilings

The existing QuotaLedger now enforces host-configured aggregate ceilings over
explicit tenant sets or globally. All applicable quota projections are evaluated
under the same existing lock before publication. Aggregate usage includes queued,
leased and payload custody and is updated by every existing reservation/release,
including unknown-effect holds. Configuration changes cannot strand current
usage outside the new ceiling; an empty ingress fork preserves aggregate policy
for recovery reconstruction. No new database or remote authority.

Policies are trusted host configuration, not information inferred from task
payload. The current archive does not independently persist or hash policy
configuration; the recovery host must supply matching policy. Shared service
ceilings are explicit tenant groupings, not per-operation keys.

## Wave A2: activation identities and elastic lifecycle

The existing runtime assigns a fresh registration token per worker activation;
restored activation identities rotate and cannot reuse old stop evidence.
The existing autoscale policy accounts for uncertain slots and does not recommend
removing occupied capacity. The new service-rate elastic recommendation reduces
backlog using bounded changes, freshness checks, warm retention, cooldown and
explicit scale-to-zero readiness. A root idle-retirement proposal excludes queued
demand, held capacity, delegated descendants and protected identities. The existing
worker registry removes an idle logical worker only after a trusted stop verifier
and exact generation revalidation. No external process is stopped or started
by these methods. Zero-ready is a trusted host assertion, not a live probe.

## Wave A3: rate-shaped dequeue and event coordination

The existing verified tenant broker uses an optional host-configured start-rate
policy before publishing an attempt. Excess work stays queued with intact
quota; every process-local start-credit bucket begins empty, including restore,
and backward clock samples grant no credit. Failed attempts conservatively
spend credit. This is not a globally coordinated distributed rate limiter.
The event-coordination helper proposes bounded keyed windows, exact replay
identity, non-discarding quiet-window coalescence with hard maximum wait,
singleton eligibility against active or uncertain ownership, and generation-
bound event/timeout wake proposals. It does not claim durable singleton locks,
timer delivery, transactional event ingestion or actual wake publication.

## Wave A4: communication affinity and content-bound scheduling

The bounded affinity planner evaluates the observed communication graph,
permits only idle and movable activations from the same tenant, policy
and generation, and calculates marginal locality gain after migration
cost. It retains destination headroom, enforces byte/move limits and
cooldown, and updates the simulated graph after each accepted move.
The artifact planner groups exact destination/content/environment/policy
identities, avoids transfer duplication and reserves bytes against finite
destination and round budgets. Missing inputs hold their consumers until
a fresh verified resident observation exists. Transfer and migration
remain advisory; no physical movement, cache publication or execution
is performed. A15 activation generation, A16 idle passivation and A21–25
lifecycle work remain subject to host integration and qualification.

## Wave A5: nested allocation authority and affinity repair

The existing global resource scheduler owns bounded, attempt-tokened nested
subleases. Children consume their parent's allocation, not a second physical
reservation. Root release cannot bypass descendants; root preemption marks
the subtree revoking, and trusted stop verification releases descendant
allocations leaf-first. Completed sublease IDs remain tombstones. Cancelling
root preemption leaves already requested child stops conservatively revoking.
The host must reserve only the undelegated remainder for direct work. No
distributed persistence or physical stop protocol is implied.
The wave-A4 exact-head test failure (dictionary mutated during affinity scan)
is repaired by nonmutating lookup. Existing regression kept intact.

## Wave A6: durable unique job admission and verified follow-up publication

The existing SwarmDurableBridge can acknowledge a unique job only after
checkpoint/readback, using the canonical tenant/task identity. It also
publishes a reconciled uncertain parent and a bounded, exact-manifest
authorized batch of dependent follow-up jobs in one recovery archive.
Children are admitted while the parent dependency barrier still holds.
Any ambiguous mutation or storage acknowledgment retires the in-memory
broker generation; restore from the actual durable archive. The host must
hold the existing exclusive run-writer lease and must not bypass the
verified owner. No external side-effect transaction or automatic replay
of a completed continuation is claimed. Uncertain write acknowledgment
requires recovery and inspection, not blind repetition.

## Wave A7: memory pressure passivation, weighted shards and overlapped pipelines

Root retirement proposals can prioritize independently observed reclaimable
bytes per estimated reload time while honoring freshness, exact activation
identity, occupied capacity and minimum retained slots. The existing verified
stop boundary remains authoritative. Weighted rendezvous placement is stable
across membership order and includes bounded resident-state redistribution
with distinct tenant/generation, byte/step budget and uncredited source release.
The copy/compute pipeline proposes separate transfer and execution intervals
only when a distinct copy engine has been verified; staging remains charged
through work completion and deadlines/horizon remain enforced. None of these
proposals moves bytes, activates workers, or claims actual GPU performance.

## Wave A8: measured policy replay and mixed-workload source qualification

The existing shadow scheduler can measure local policy-computation elapsed
nanoseconds over the same pinned workload and rotate policy order across
repetitions; raw samples, median, p95, trace identity and replay outcomes
are retained. Wall-clock computation is distinct from simulated work.
The integration test exercises real SQLite persistence, shared tenant
quota, virtual worker partitions, ranked durable leasing, uncertain
restart custody and atomic continuation publication. The verifier in
this test is a fixture, not external effect authentication. No external
competitor measurement, physical native execution, throughput advantage
or product-wide qualification is claimed.

All 36 alternative targets have a partial source implementation or
qualification harness. A35/A36 remain measurement and qualification
work, not completed competitor benchmarks. Original 72-target source
register remains unchanged. Combined 108/108 partial source coverage;
independent competitive qualification remains 0/108.

## Wave A9: authoritative event wait gates and singleton custody

The existing verified tenant broker derives singleton scope from the tenant
and host-provided key; both heap and exact leasing honor the gate, with
one occupied slot per scope and unknown effects retaining ownership.
The runtime reconstructs the singleton occupancy index on restore and
rejects conflicting holders. A wait intent binds a digest; the durable
bridge authenticates its receipt through a trusted verifier, opens only
the exact wait, and checkpoints/readbacks before permitting dispatch.
Ambiguous publication retires the owner. New gate-bearing runtime
snapshots use version 3: older readers fail closed rather than silently
ignore gates. Versions 1/2 remain readable and the existing delta archive
can carry version-3 snapshots. The existing exclusive run-writer and
authenticated event or clock receipt producer remain prerequisites; no
external timer daemon, cluster-global singleton, or independent evidence
transport is claimed. Regression fixtures cover both lease paths,
tenant isolation, uncertain restart, real SQLite reopen, and failed wake.
Prior wave A8 exact head passed 89 focused tests and 183 architecture
mappings; that is not a substitute for A9 exact-head qualification.

## Wave A10: durable ingress-policy identity

New verified tenant checkpoints bind a canonical fingerprint of effective
admission policy: default/tenant/shared quotas, member scope, fairness
weights, ingress and dispatch rates. Accounting alone does not alter this
identity. Legacy sidecars retain their original checksum and remain readable;
new sealed checkpoints refuse a mismatched restore host. Restore also checks
verified task ownership and same-tenant dependencies before republishing
metadata. This is an integrity binding within the existing archive, not a
signature, independent authorization, or a persistent rate-credit ledger.
Live policy changes require the trusted owner and a new durable checkpoint.
New regressions cover canonical ordering, accounting stability, rejection
of relaxed quota on restore, and invalid sidecar integrity.

## Wave A11: host-owned timer and authenticated event execution

The existing recovery archive now carries a reserved, exact run/tenant/task
host-wait intent in the task payload; its existing wait digest independently
binds that envelope. The trusted owner driver submits through the canonical
durable bridge and scans restored queued waits for due UTC timers. Due timers
are ordered by deadline and identity, batch bounded, and published using the
existing wait gate only after checkpoint/readback. Restart needs no secondary
timer database. Trusted event collectors sign exact wait/evidence/timestamp
receipts with tenant/source-scoped HMAC-SHA256 keys; cross-wait, forged,
out-of-window and conflicting receipts fail closed. The checkpoint retains
receipt digest; the trusted collector must keep the signed envelope for audit.
Ordinary success/uncertain outcomes and uncertain-attempt reconciliation now
have durable checkpoint/readback wrappers; ambiguous writes retire the owner
instead of acknowledging an effect or releasing custody by replay.

Host registration, production credential provisioning/rotation, UTC clock
integrity, durable external event intake, service-loop invocation, physical
worker verifiers, and independent runtime/competitor qualification remain
required. This is a concrete executable local owner API, not a deployed
daemon, distributed transport, or claim that all 108 targets are complete.
Six focused regression cases cover restart, signature attacks, exact envelope
custody, durable completion, ambiguous write, and durable retry.

## Wave A12: authenticated worker and independent reconciliation receipts

The canonical broker's existing verifier injection now has a concrete
HostWorkerAuthority implementation. Each signed receipt binds run, issuer,
worker, task, attempt token, exact action (including continuation digest),
and independently pinned artifact bytes. Verification checks the receipt
digest, HMAC, source scope, action grant, actual artifact digest and a required
independent content-validator callback before the broker accepts an effect.
Completion and reconciliation action grants cannot be mixed for an issuer
scope. The host remains responsible for independently provisioned keys,
persistent immutable receipt/artifact custody, and the semantic correctness of
the physical evidence validator. An unavailable resolver/validator fails
closed. A fixture verifies signed completion through real SQLite recovery;
an adversarial fixture checks wrong worker/attempt/run/key, artifact mutation
and action escalation. Previously inherited worker-refusal test fixtures now
use explicit verification only where a successful synthetic outcome is intended.

### A12 continuation receipt separation

Atomic uncertain-parent reconciliation and follow-up admission now accept
a separately signed continuation-manifest receipt alongside the exact
reconciliation receipt. The old single-digest interface remains compatible
with existing host verifiers, but the strict signed verifier refuses it for
two different actions. Credentials cannot be reused across distinct issuers,
and one issuer cannot receive both effect and reconciliation roles even at
different worker scopes. The new real-SQLite regression exercises refusal
with insufficient authorization followed by successful durable publication
with distinct action receipts. Key custody and the actual independent
physical evidence validator remain externally provisioned.

## Wave A13: end-to-end local owner dispatch cycle

HostDispatchService connects the executable timer driver to canonical ranked
durable leasing, a supplied authenticated worker transport and evidence-bound
completion. It publishes/readbacks the lease before handing off immutable
payload bytes; the transport executes outside the scheduler locks and may
receive each attempt only once through that cycle. Any transport exception or
malformed reply durably holds the original attempt as uncertain, preserving
worker and tenant capacity. Signed outcomes use the actual verifier; invalid
or ambiguous acknowledgements stop the owner and require archive restoration.
The cycle is nonreentrant and admits only an explicit authorized candidate
set. Regressions exercise the complete local SQLite timer-to-transport-to-
signed-outcome route, plus transport loss and no repeated launch.

This completes the in-process owner execution path, not the application
deployment. A host must connect its actual worker transport, durable immutable
receipt resolver, physical evidence validator, run lease renewal and service
tick. The test signer/validator is synthetic; no native GPU/cluster/device
or independent comparative result is claimed.

## Wave A14: physical local worker and durable signed evidence custody

SQLiteWorkerCustody owns a separate evidence journal (not a second scheduler).
An atomic exact attempt tombstone and bounded logical storage reservation
precede physical launch. Concurrent repeats cannot start the same token;
a started attempt with no committed receipt remains uncertain forever until
explicit recovery. Result publication binds the immutable signed receipt and
artifact in one transaction and verifies readback. Reopen preserves custody
and policy ceilings, while mismatched identities, changed receipts, capacity
exhaustion and non-private storage fail closed. The journal is not encrypted
or a distributed service; the trusted host owns directory and backup policy.

LocalSubprocessTransport actually executes an isolated Python interpreter with
a fixed program for three bounded pure operations: text SHA-256, integer sum,
and canonical JSON SHA-256. Tenant/worker grants are explicit. No task can
select arbitrary commands, executables or shell arguments. The host verifies
the returned result independently before signing; the broker validates
recomputed semantics against the persisted admitted input after SQLite
readback. The exact same signed receipt can be read after restart without
rerunning the physical process. An incomplete attempt never re-launches.
Four regressions cover real child execution, durable end-to-end dispatch,
concurrent tombstones, conflicting evidence, capacity and uncertain replay.

This is actual local CPU work within the explicit operation scope, not
general code/tool execution, production model inference, process sandboxing,
or deployment qualification. Physical disk headroom, encryption, external
receipt intake, orchestration startup, lease renewal and independent
competitive measurements remain open.

## Wave A15: committed-result crash reconciliation

The SQLite evidence journal migrates v1 to v2 transactionally and retains
a separate immutable second-issuer reconciliation receipt per original
attempt. Both the result and subsequent reconciliation are SHA-bound,
capacity-accounted and independently readable. The original committed
worker receipt is resolved and revalidated using the original worker
authority and deterministic operation semantics; the inspector signs a
distinct committed-recovery receipt that references the original receipt,
artifact and exact admitted payload. The existing canonical broker
revalidates the inspector's authority and checkpoints/readbacks before
releasing the uncertain task. No subprocess is launched during recovery.
Pending or mismatched attempts remain uncertain. This establishes a
recoverable local pure-job effect path, not a general external side-effect
or physical-stop proof. Two regressions cover the lost owner checkpoint
window and rejection of unproven attempts.

## Wave A16: managed local dispatcher lifecycle and writer fencing

A concrete managed host startup now claims the existing SQLite run using
revision CAS and a fresh process-generation writer identity. It refuses
nonempty or nonfenced fresh runtimes, unrelated run steps, missing tenant
sidecars and fresh-runtime replacement of existing archives. Recovery
preserves uncertain attempts and restores the sealed ingress policy;
the new generation checkpoints before accepting work. The managed public
submission, event, timer/dispatch tick and committed-recovery boundaries
renew the real owner lease, and a failed renewal retires the stale owner.
Transport timeout must leave a configured lease margin. Exact checkpoint
readback now also compares the actual checkpoint identity/revision and
owner when backed by the real run store. Stop retires locally without
fabricating physical stop or early release; takeover waits for stored
expiration. New tests exercise two-generation takeover, stale owner
refusal, actual process execution on both generations and unsafe bootstrap.

This is an opt-in host lifecycle API, not yet wired into the app's global
startup or daemon. Automatic candidate authorization, heterogeneous
resource adapters, independent device qualification and external worker
transport remain open.

## Wave A17: bounded domain compute catalog

The fixed physical transport now supports nine explicit operations including
chunked content manifests, token histograms, sparse integer dot products,
exact lexical retrieval ranking, shortest-path witnesses and dependency
topological order. These are useful archive, retrieval, game-routing and
workflow building blocks. The owner uses separately expressed algorithms
(Dijkstra versus Bellman-Ford, heap indegrees versus repeated frontier
selection, independent token counts) and exact canonical bytes, not
approximate scores or worker assertions. Admission bounds input structure,
graph size, weights, result capacity and allowed capabilities before the
first physical attempt. Two regressions exercise the real child process
for all added operations, ties, unreachable and cyclic graphs, malformed
inputs and refusal before tombstone creation. No neural inference claim.

## Wave A18: durable cancellation, dependency propagation and bounded outer history

The canonical durable bridge can now cancel owned queued tasks, release quota
and checkpoint/read back atomically at the owner boundary. Terminal parent
failure propagation uses canonical runtime dependency logic, tenant accounting
and one durable capture; uncertain attempts are never treated as terminal
failures. The real SQLite run store adds a revision-bound lease relinquish
operation and dedicated checkpoint-only retention that rejects workflow steps,
stale writers and mismatched latest checkpoint identity. Retained revisions
are never renumbered. Managed owners expose explicit graceful close, periodic
outer retention and durable cancellation/dependency propagation. Source and
mirror files retain parity. New tests cover cancellation and dependency
propagation plus independent run-store retention and exact-owner takeover.

## Wave A19: installed private local dispatcher service

Install the repository package and invoke the actual script:

    skeleton-jeeves-dispatch --directory /absolute/private-dispatch init --tenant owner --operation integer_sum --operation shortest_path
    printf '%s' '{"kind":"submit","tenant":"owner","task_id":"job-1","operation":"integer_sum","input":[1,2,3]}' | skeleton-jeeves-dispatch --directory /absolute/private-dispatch enqueue --id request-1
    skeleton-jeeves-dispatch --directory /absolute/private-dispatch serve
    skeleton-jeeves-dispatch --directory /absolute/private-dispatch command --id request-1
    skeleton-jeeves-dispatch --directory /absolute/private-dispatch result --tenant owner --task job-1

Use a new absolute directory with an existing trusted real parent. Initialization
provisions separate random worker, inspector and local event credentials in
private POSIX files, pins the complete policy to the durable run, and creates
an explicit owner-only service lock. No credentials print. This is a same-UID
local administrative interface, not a remote or multi-user sandbox. State and
credentials are not encrypted; protect the directory and backups externally.
POSIX ownership enforcement is mandatory; Windows is explicitly unsupported.

The installed command accepts a durable JSON inbox, including exact retry-safe
submission, dependency IDs, queued cancellation, singleton, UTC timer,
local-operator event wait/signal, committed-effect reconciliation and stop.
For example use fields timer_ms or event={"selector":"approve",
"not_before_ms":...}; signal commands carry tenant, task_id, event_id, selector
and an evidence JSON value. Signals assert a local operator event, not third-
party verified truth. Acknowledgements are checked against the live writer in
the same SQLite transaction; stable request identities handle process failure
between task checkpoint and acknowledgement. The operator service derives
ranked candidates from admitted durable metadata, never a caller-supplied
priority observation. Admission and replay capacity, checkpoint retention,
grants and real worker evidence are bounded. The private local service
automatically executes admitted work, polls timers, propagates terminal
dependency failures and reconciles committed local results. It does not
auto-retry uncertain physical work. Graceful stop releases only the exact
live ownership lease; crashes require genuine expiration/recovery.

The foreground command is deployable under an operator-selected supervisor;
the main app's default startup remains unchanged. Nine fixed compute
operations execute as real subprocesses; native inference, external effectful
tools, distributed execution and physical device migration are not included.
The five new tests cover actual CLI child execution, restart/admission replay,
tenant result boundaries, stale ack refusal, credential-policy seal and
competing service process lock. Exact-head qualification is still required.

## Wave A20: concurrent physical workers and fenced heartbeat renewal

The installed service now admits and executes up to the configured worker
count (one to 32) in parallel. Each selected ranked task obtains its real
worker/tenant grant and a durable exact lease before any thread starts.
Immutable handoffs execute in a bounded pool without broker locks. A
single owner settles signed results, renews the real writer lease and
renews exact live worker attempts when their deadlines approach. Lost
writer authority or expired attempt renewal retires the generation; it
cannot publish further results or convert uncertainty into retry. Workers
already started may finish durable evidence; recovery independently
revalidates that evidence. One failed transport preserves its attempt
custody while unrelated work may complete. The application exposes per-
task and aggregate batch outcomes. Actual process-overlap, mixed failure
and expiry regressions were added. The configured worker count is a
physical local concurrency bound, not a claim of measured scaling speed.

## Wave A21: actual pinned CPU GGUF worker execution

The installed dispatcher can now run a real local GGUF generation through
the canonical LocalInferenceEngine and llama.cpp adapter. Configure
the existing init command with an explicit additional operation
gguf_generate and --gguf-policy pointing to an owner-private JSON
file. The JSON has exact fields: executable, model, runtime_sha256,
model_sha256, context_tokens, threads, batch_tokens, kv_bytes_per_token,
reserve_bytes, timeout_seconds, max_output_tokens, runtime_libraries
(array of filename/digest pairs; empty only when consciously relying on
the trusted host loader), workspace_db (absolute private existing SQLite
anchor or null for the dedicated dispatcher database). Supply exact
SHA-256 pins and a safe context/KV budget. The initializer verifies
actual artifact identities and seals the canonical execution profile.
The writer lease must be at least fifteen seconds longer than the
largest configured execution timeout. Startup revalidates pins;
commands can never select model paths, executable flags or credentials.

A submit command with operation gguf_generate takes input
{"prompt":"...","max_output_tokens":32,"seed":0}; seed is optional.
The admitted UTF-8 byte upper bound and pinned context protect the
shared input/output window. One explicitly capable physical worker
uses the existing local inference engine without result caching,
CPU-only configuration and measured RAM/CPU admission. If workspace_db
points to the same application workspace, the canonical inference
lock excludes concurrent generation by that service. It is not a
system-wide lock covering unrelated workspace paths.

The native backend now exposes exact bounded non-content execution
receipt frames. Durable artifacts bind the entire admitted payload,
model, runtime, profile, output, response identity and reconstructed
native receipt digest. Reconciliation validates the original native
receipt and distinct inspector receipt without re-execution. Historical
reads work even if the operator removed the asset. Native receipt
hashing and host HMAC prove trusted local execution custody, not
factual answer accuracy or independent third-party attestation.
Token counts remain backend estimates. No downloaded assets or
claimed pretrained benchmark result. The explicit CLI fixture tests
exercise actual native adapter subprocess boundaries, not trained
weights; real GGUF assets and device qualification remain operator
and CI responsibilities. Default app boot is unchanged.

## Wave A22: rolling complete terminal history and bounded resident scheduler

Initialize with --max-jobs for the resident checkpoint window and an explicit
larger --history-jobs (up to 100000), --history-mib, --inbox-mib and
--evidence-mib appropriate to physical disk capacity. Existing configurations
without a history policy retain their earlier limits and database schema.
The private archive stores exact terminal task records, source checkpoint
identity, original verified receipt reference, tenant, and a domain-separated
HMAC. Publication is a live-owner/latest-checkpoint SQLite transaction before
resident deletion. Leaf-first compaction refuses any resident reference or
uncertain/active effect. The scheduler forgets those exact terminal entries
only after archive readback and captures its new resident state. If a crash
occurs between the two commits, restart reuses the original immutable archive
row, not a second execution. The permanent archive identity prevents submitting
any old task under a new request, and same-tenant archived successful parents
can satisfy new dependency gates after evidence revalidation. Historical
result reads still verify the original result and any inspector reconciliation.
Counters are checked by the streaming audit-history command. Finite logical
limits remain explicit: no physical disk guarantee, indefinite retention or
cross-host archive claim. Four regression tests cover rolling beyond the live
window, dependency retention, archive/capture crash recovery, tenant refusal,
tampering, historical capacity and no duplicate physical execution.

## Wave A23: canonical application host integration

The installed command is accessible directly through python -m skeleton app
dispatch with its existing complete argument contract. JeevesApplicationRuntime
also accepts three explicit host provisions: dispatcher_directory,
dispatcher_policy_sha256 and dispatcher_authorize. They must be supplied
together. The authenticated host can now call dispatch_request with exact
context, action, request identity and arguments, using the real durable
dispatcher inbox and result custody. The gateway derives independent opaque
identities by authenticated tenant/project/principal/run for jobs, requests,
dependencies, singleton keys, and events. It rechecks sealed policy and
database inode on each authorized operation. The explicit authorizer receives
immutable exact request bytes and the authenticated context. No permission is
derived from prompts or generated actions. Every read is also authorized;
protected priority lanes, global stop, credential/policy changes, foreign
scope and unknown actions are refused. The workbench never starts another
scheduler or executor. Actual foreground service execution remains explicitly
operator-managed, and no new public API route or automatic startup is enabled.
Regressions cover two project scopes with identical client IDs, denial and
priority boundaries, and the real canonical application CLI-to-job-to-result
path. This is a local authenticated host binding, not a remote cluster.

### A22 qualification repair: sealed journal rollover

A23 exact-head CI exposed four terminal-history tests failing because the
ordinary verified delta codec intentionally forbids losing tenant ownership
identities inside a journal. Compaction now closes that journal segment only
after every forgotten identity is sealed in its separate terminal archive and
verified by readback, retaining the durable predecessor outer checkpoint.
It publishes a new single-full-anchor segment using the same manager,
monotonic sequence, tenant policy, and retention ceiling. The generic delta
encoder and replay guard remain unchanged. A failed/ambiguous publication
retires the generation and does not undo SQL commits. Startup audits archived
identity seals and counts before admitting new tasks. Added a regression
checking the full anchor and independently reconstructible predecessor.

## Wave A24: verified result-linked application workflows

A submission may now specify up to eight exact result bindings and an
explicit binding_deadline_ms (at most seven days beyond inbox admission).
Each binding has source_request_id, source_task_id, source_path and
target_path. Paths are bounded arrays of literal object keys or list
indexes; an empty path selects the root. Targets must be existing null
placeholders, with no overlapping paths, no expressions or interpolation.
For example, a second integer_sum job can use input [null, 4] and bind
source_path [] to target_path [0] of an earlier integer_sum result.
The source must be an earlier durable same-tenant submit command whose
task identity matches the accepted acknowledgement. Earlier deferred
submissions can form chains; forward references and cycles are refused.
Uncertain effects remain pending; failed sources reject and deadlines
expire. The inbox rotates bounded indexed scans so deferred work cannot
starve later event signals, cancellation or unrelated submissions.
cancel-pending can settle an earlier unadmitted linked request without
executing it. Admitted tasks still require normal queued cancellation.

Resolved bytes, source receipt and optional reconciliation digests and
exact value hashes are sealed into the canonical task's scheduling
metadata. The worker receives only the fully materialized operation.
Replay after admission checks original request identity and reconstructs
lineage without re-executing or reapplying an expired deadline. Historical
result reads revalidate immediate parent receipts and replay their direct
substitutions, not an unbounded recursive traversal. Parent results may
be archived outside the resident window. The authenticated Jeeves host
gateway derives scoped source request/task IDs and supports pending
cancellation under explicit authorization. Six tests cover physical
multi-stage jobs, archive traversal, fair waiting, expiry, malformed
paths, cross-scope refusal, crash replay and host integration.

## Wave A25: atomic graph submission and verified workflow status

The private CLI exposes workflow-submit --tenant OWNER --id ID and
workflow-status --tenant OWNER --id ID. Submit JSON with deadline_ms
and jobs (at most 32); each job includes request_id, task_id, operation,
input and optional dependencies, bindings, priority, singleton, timer_ms
or event. All dependency and binding edges must reference exact internal
nodes. The deterministic topological compiler refuses cycles, duplicate
identities, out-of-policy operations, oversized templates and invalid
gates before publishing any commands. Static operation inputs are
validated first. Unbound ordering edges become receipt-verified
prerequisites; result edges use exact value binding. No dependency
requires indefinitely retaining a settled resident task.

The manifest and every canonical command are published in a single
SQLite transaction, with a domain-separated seal, bounded capacity
accounting, no partial adoption of overlapping request identities and
exact idempotent replay. Reordered equivalent graphs compile to the
same identity. A graph acceptance is not a promise of atomic physical
effects: actual task admission, execution and uncertain custody remain
canonical per-node operations. Workflow status revalidates manifest and
command identity and independently reads the current canonical task
outcomes and receipt references. The authenticated host supports scoped
workflow-submit and workflow-status; a graph submission must receive
both an exact graph grant and separate authorization for each child.
Four regressions cover actual fan-in and predecessor compaction,
transactional refusal, manifest/command integrity and host grants.

## Wave A26: durable workflow lifecycle, capacity waiting and cancellation

Workflow creation now reserves every task identity as well as each request
identity. Existing sealed graphs migrate to a durable membership index in
one transaction. Standalone work cannot claim an already reserved graph
task. The owner checks manifest membership before admission. New graph roots
share the same bounded admission deadline and defer on temporary resident
capacity or ingress pressure rather than being permanently rejected merely
because a sibling occupies the scheduler.

The new workflow-cancel --tenant OWNER --id FLOW --request-id REQUEST command
and authenticated host action request graph cancellation. An immutable,
domain-separated cancellation intent is published under the live owner before
any member changes. Queued tasks receive canonical durable cancellation,
unadmitted requests receive exact rejection acknowledgements, and admitted
tasks with lost acknowledgement are recovered without another execution.
Succeeded or failed effects remain historical facts. Unresolved physical
effects retain their exact lease and accounting; cancellation does not claim
that they stopped. On takeover, interrupted cancellation intents are processed
before normal ingress and physical dispatch. Repeated cancellation returns the
original receipt. Six regressions cover root pressure, deadlines, reservation,
queued/unadmitted cancellation, interrupted cancellation, uncertain effects
and the separately authorized host workflow-cancel action. The graph creation
collision scan is bounded by the configured inbox ceiling but is linear in
historical commands; production-scale latency remains to be measured.

## Wave A27: indexed ingress ledger and pre-transport proof

A one-time transactional migration builds the valid historical task index
and exact logical command/manifest capacity counters. New standalone and
graph submission reserve capacity, index their canonical identities and
publish all bytes in a single transaction; conflict rollback includes
capacity accounting. Graph collision lookup is bounded by graph size using
the task index, not by historical command count. The explicit audit-ingress
command streams and independently revalidates the inbox, manifest seals,
member and cancellation records, indexed task identities and counters.
Startup runs the audit before acquiring the real worker owner. At physical
candidate derivation, every queued task is bound to its exact admitted
command, immutable input or verified lineage, ownership, priority, graph
manifest, cancellation state and acknowledged admission. A captured but
unacknowledged task cannot physically execute through the installed service.
The five added regressions cover transactional retry/conflict accounting,
migration, corruption refusal, lost admission acknowledgements and
post-admission graph manifest tampering. Logical counters and indexed
admission do not certify physical storage capacity or throughput.
