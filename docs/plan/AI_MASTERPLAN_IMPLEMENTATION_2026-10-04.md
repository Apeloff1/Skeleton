# AI masterplan implementation depth — 2026-10-04

This pass deepens the existing P3-T2 continuation owners. It preserves the
32 scheduled / 165 queued partition, every completion checkbox and signature,
and the independent exact-head closure requirements. The implementation is a
reviewable candidate; local tests do not establish landed or production evidence.

## Implemented behavior

| Owner | Concrete behavior | Executable evidence |
| --- | --- | --- |
| `P3T2-TRAINING-01` | The existing SQLite training repository commits full reference-model counts, document cursor and cumulative usage together with a fenced checkpoint. An interrupted trainer reloads those counts and skips committed documents; completed retries reload the durable artifact. | `test_p3_training_resume.py`, `test_p3_local_training_evaluation.py` |
| `P3T2-TRAINING-01` | Reference control-plane retries bind the complete spec, worker plan, dataset metadata and corpus. Checkpoint descriptors must match canonical stored content. Gate digests include threshold policy, and post-training accepts only decisions issued for the exact admitted training receipt. | `test_p3_training_evidence_integrity.py` |
| `P3T2-LEARNING-01` | Curriculum evidence binds stage thresholds, registered episode traces and one exact policy. Verifier candidates consume measured local benchmark receipts with the same model and training identity. Arbitrary evaluation strings, mixed policies and altered results fail closed. | `test_p3_learning_programs.py`, `test_p3_learning_foundation_acceptance.py` |
| `P3T2-MULTIMODAL-01` | Ingestion stages validation before publishing the asset, blob, record or text projection. Rejected conflicts cannot poison retrieval. Reads verify issued record, content and text identity; speech receipts retain a verified ordered chain. | `test_p3_multimodal_integrity.py`, `test_p3_multimodal_foundation.py` |
| `P3T2-LIFECYCLE-01` | Bounded reported per-input output comparisons produce registry-issued migration evidence. Applying a migration atomically activates the target and deprecates the source; rollback restores the captured baseline under the exact migration history. Numeric proposals alone cannot apply a migration. | `test_p3_model_migration.py`, `test_p3_model_lifecycle.py` |
| `P3T2-DATA-01` | Materialized ingestion stores original source bytes and exact document sequences, computes observed quality, versions datasets transactionally and durably fences source revocation/deletion. | `test_governed_training_data.py` |
| `P3T2-TRAINING-01` | Real NumPy recurrent SGD persists full weights, optimizer settings, epoch/document cursor, cumulative budgets and observed loss. Interrupted training resumes to bit-identical weights. | `test_p3_neural_training_resume.py` |
| `P3T2-LEARNING-01` | Executable local episodes commit actual policy/environment effects, receipts and cursors together; curriculum and qualification derive from issued execution and measured evaluation. | `test_p3_post_training_execution.py` |
| `P3T2-MULTIMODAL-01` | Bounded text exports bind actual projected documents to assets, projections, rights, lineage and simulation purpose; native dataset ingestion preserves the complete source manifest. | `test_p3_multimodal_training_projection.py` |
| `P3T2-LIFECYCLE-01` | SQLite persists and validates the complete lifecycle evidence graph, reconstructs issued decisions after restart, serializes independent connections and supports validated backup/restore. | `test_p3_model_lifecycle_persistence.py` |
| Existing provider owner | Derived artifacts activate through an explicitly declared local provider with architecture acknowledgement, conservative governance, admission, actual usage and cancellation. | `test_local_provider_activation.py`, `test_local_provider_runtime_guards.py` |
| Existing engine API owner | Authenticated inventory exposes provider availability; durable handoff recovery reconstructs the original accepted lineage under current read authority. Cancellation waits for the actual local worker to exit before terminalization. | `test_engine_routes.py`, `test_engine_handoff_recovery.py`, `test_local_inference_cancellation.py` |
| `P3T2-TRAINING-01` | Two to four actual spawned local NumPy ranks commit deterministic complete synchronous barriers with full averaged weights and rank receipts. Worker death/timeout leaves the previous checkpoint intact; recovery matches uninterrupted execution of this algorithm. | `test_p3_local_data_parallel_training.py`, `test_governed_training_cli.py` |
| `P3T2-TRAINING-01` | Tenant/trust-bound CAS archives full native checkpoints and original operator admission. Restore fences workers and checks source authority; protected retention preserves latest/recovery references. A fresh training database can republish all three trained model variants without updates. | `test_training_checkpoint_archive.py`, `test_governed_checkpoint_recovery.py` |
| `P3T2-LEARNING-01` | The existing evaluation ledger persists actual independent verifier decisions per case and derives calibration/error rates and baseline regressions. Issued measured qualification rejects fabricated scalar metrics and reuses completed case records after restart. | `test_measured_local_verifier.py` |
| `P3T2-MULTIMODAL-01` | Verified intake decodes actual bounded PNG/JPEG/WebP pixels and PCM WAV samples, replacing caller geometry/timing with measured evidence and rejecting corrupt/oversized/forged inputs before publication. | `test_multimodal_media_validation.py` |
| `P3T2-MULTIMODAL-01` | Existing speech session contracts execute ordered verified audio and final transcript commits with isolated durable recovery; timed video evidence fuses deterministic modality scores after rights/time/simulation filtering. | `test_p3_live_speech_execution.py`, `test_p3_video_evidence_fusion.py` |
| Existing engine API owner | The checkpoint pins the exact local artifact and inference seed before first dispatch; unfinished restart rejects model/configuration substitution while preserving committed usage and completed-result replay. | `test_engine_local_provider_binding.py` |

The [operator guide](GOVERNED_LOCAL_MODEL_DEVELOPMENT.md) documents the new
`skeleton-train-governed-model` command and the concrete restart/deletion/rollback
path. The assembled multimodal/neural/lifecycle acceptance test closes and reopens
all durable authorities, executes held-out local suites, applies and compensates
a migration, then proves revoked/deleted/corrupt/failed-quality sources cannot
be reused.

`test_governed_model_engine_acceptance.py` also runs the reference and neural
CLI through an authenticated HTTP engine with network sockets blocked. It
reopens both training databases, replays completed training without updates,
checks actual governance/admission/usage receipts and provider inventory, then
reopens the engine database and verifies execution replay and cancellation.

`test_p3_training_lifecycle_acceptance.py` assembles the durable native trainer,
close/reopen artifact reload, actual local model evaluation, MBOM identities,
measured output parity, candidate migration and rollback. The existing learning
acceptance chain also executes local benchmarks instead of placeholder evidence.

## Ownership, persistence and bounds

The native resume format is declared in
[`machine/ai_training_resume_contract.json`](../../machine/ai_training_resume_contract.json).
Full payloads and execution bindings use additive tables in the existing
`TrainingRepository` SQLite database. Checkpoint identity includes payload
identity; legacy digest-only checkpoints remain readable but cannot provide
resumable model state. No separate service, state owner or provider boundary is
introduced.

Reference execution remains a single-worker n-gram count estimator; the second
implementation wave also adds a real single-worker NumPy recurrent SGD trainer.
Document batches, individual document bytes, total corpus bytes and checkpoint
payload size are bounded before execution or commit. Immutable execution
bindings preserve document boundaries, model order and split identity. Budgets
apply to total committed work across restarts. Worker fences are checked inside
the SQLite write transaction, including terminalization.

Foundation training admission, recovery and evaluation methods serialize
identity transitions and protect stored receipts from caller-owned mutable
containers. The foundation content-addressed store remains an in-memory witness;
the SQLite native trainer owns durable model recovery.

Learning benchmark receipts prove local execution, result classification and
identity binding. Held-out population labels and contamination fingerprints
remain declarations; they do not prove real-world dataset disjointness.
Lifecycle parity comparisons record verifier-reported observations. The assembled
test supplies actual local evaluation outputs, but the registry itself does not
authenticate external observation provenance or execute production routing.
Its migration and rollback state is now optionally durable SQLite candidate
control, with full graph validation and version fences across connections.

## Failure, observation and rollback

Resume fails closed on missing or corrupt payloads, execution-binding drift,
legacy checkpoints without model state, stale worker leases and resource
exhaustion. Checkpoint/receipt digests and durable telemetry expose the committed
cursor, work usage and model identity. A failed batch retains the prior valid
checkpoint; recovery fences old workers before continuing.

Candidate evaluation rejects unissued or contradictory receipts. Multimodal
conflicts preserve the prior searchable record. Model migration reserves history
capacity for compensation before changing either model and rejects stale
rollback evidence.

Code rollback must preserve the training database and its payload tables. Older
code cannot consume new payload-backed checkpoint identities; stop resume workers
and retain a compatible code/database pair rather than deleting checkpoint state.
Model rollback is an explicit compensation receipt that restores the source and
withdraws the target while retaining history. Nothing in this pass automatically
promotes a model, release or masterplan owner.

## Validation and remaining work

The expanded **AI Governed Training Pipeline** workflow checks out the
exact source head, validates the bounded contract, compiles both runtime packages,
runs focused and assembled regressions, and separately runs the canonical
architecture, construction, capability-interface, state-topology and provider
bootstrap gates.

Local verification of the assembled candidate passed **291 focused, adversarial
and contract tests**. Changed runtime and test files passed Ruff, compilation and
whitespace checks. Architecture, construction, capability-interface,
state-topology, provider-bootstrap, bounded-resume, continuation, storage-candidate
and data-candidate validators passed. CI must independently repeat these checks
on the submitted commit.

The data candidate's provenance now points at landed squash commit
`573658f64efc0ae8a52e08ddec256f98ce963617`, whose data tree matches the recorded
candidate tree. The original branch implementation SHA is retained separately.
Continuation tests now expect the validator's task-qualified rejection messages.
These repairs confer no closure authority.

The second wave repairs the global AI-file-tree mirror drift, restores an honest
remaining independent verification gap at `VOL-248`, and refreshes both native
and learning obligation snapshots from the authoritative masterplan. It also
repairs inherited repository traversal, dependency, retrieval, taxonomy and
budget/recovery fixture failures while preserving authority fences. Global
validators and those reconciled domain suites now pass locally. The consolidated
second-wave run passed **1,675 tests and 29 subtests across 119 test files**;
one redundant repository scan was deselected and the provider-bootstrap gate
ran separately. The final CLI numerical-dependency binding change also passed
**37 targeted CLI/engine tests**. All changed Python files passed Ruff and
compilation, and the architecture, construction, capability-interface,
state-topology, masterplan, file-tree, continuation, training/learning execution,
closure-evidence, resume, pipeline and provider-bootstrap gates passed locally.
The earlier 291-test count describes the first wave. Remote CI must repeat
verification on the submitted head.

The third wave passed **1,844 broad regressions and 164 final focused tests**.
Four assembled lifecycle cases were repeated after replacing their opaque image
fixture with actual verified PNGs: the combined result is **2,004 distinct tests
plus 29 subtests across 129 test files**. One redundant repository scan remained
deselected, and the mandatory provider-bootstrap scan passed separately. All
37 changed Python files passed Ruff, compilation and Python 3.11 syntax checks.
The assembled contract now validates 15 contracts, 14 API owners and 29 executable
test files, including explicit local-parallel, archive and measured-verifier
acceptance. Canonical architecture, construction, interfaces, state, masterplan,
file-tree, continuation, execution, closure-evidence and resume gates also passed.

Remote distributed collectives, independently authenticated production evaluation,
production model-routing migration and independent masterplan closure remain
outside this bounded implementation. No queued volume, completion checkbox or
signature is removed or fabricated.
