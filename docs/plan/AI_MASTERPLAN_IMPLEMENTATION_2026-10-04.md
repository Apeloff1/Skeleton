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

Native execution remains a single-worker reference n-gram count estimator.
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
Its migration and rollback state remains bounded, process-local candidate control.

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

The new **AI Training Resume and Evidence Integrity** workflow checks out the
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

Pre-existing global blockers identified during this pass include unrelated
AI-file-tree mirror drift, a depth-pass gap inventory violation at `VOL-248`,
and historical native-training backlog obligation drift at `VOL-133`. They require
their own reconciliation and cannot be treated as green because bounded domain
tests pass. Neural optimizer resume, distributed collectives, independently
authenticated production evaluation and durable model-routing migration remain
outside this bounded implementation.
