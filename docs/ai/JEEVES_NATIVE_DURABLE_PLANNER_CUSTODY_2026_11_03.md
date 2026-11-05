# Jeeves native durable planner custody (source-only, November 3 2026)

## Scope

This extension to PR #4700 adds **principal-bound agent checkpoint history**
to the canonical protected execution-spine SQLite connection, rather than
opening an unanchored SQLite file or replacing the existing native request,
model receipt, source manifest, WAL or outbox authorities.

The additive `jeeves_native_runs`, `jeeves_native_checkpoints`, and
`jeeves_native_inflight` tables are contained within the same descriptor-
anchored private database, run under its existing SQLite transactions.
Records bind tenant, operator, installed model digest, tokenizer digest,
run ID, goal text, budget and user-scoped metadata. A capped chain of
consecutive checkpoint hashes rejects corrupted or missing interior entries,
mismatched roots, replayed sequences and changed principals. This is a hash
chain for record integrity, **not** HMAC authenticity against a privileged
adversary who can rewrite all private DB records.

**Critical behavior**: the strict Jeeves runtime journals native-call intent
*before* invoking the model and clears that intent *only after* the native
provider has confirmed an authoritative SQLite receipt and Jeeves has
committed a post-response checkpoint. A crash between those events leaves an
intent row that forbids automatic replay even if the next prompt could differ
because unpersisted working memory changed.

A successful or failed terminal answer is stored as a single bound
`jeeves_native_terminal_results` receipt **after** a terminal checkpoint.
This record carries the exact displayed answer, outcome and usage, and is
replayable without a second generation. A crash in the narrow gap between
the terminal checkpoint and receipt write leaves the answer unavailable and
must be investigated; it never licenses a new model call. Terminal replay
verifies the checkpoint tip, payload bytes, scope and model digests.

The existing cross-process `SessionGate` is held across the complete agent
run or explicit resume, rather than only across each GGUF request. Native
SQLite itself still owns per-request serialization and uncertain-effect fences.

## Operator workflow

`native_cli` exposes three **operator-initiated** commands (the provided
`task.txt` is a private local file, not a repository artifact; source proof
and model installation must already have been independently approved):

```bash
python -m skeleton.jeeves.agent.native_cli \
  --mode durable-agent --run-id jeeves_job_001 \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --task-stdin < /approved/private/task.txt

python -m skeleton.jeeves.agent.native_cli \
  --mode durable-agent --run-id jeeves_job_001 --inspect-run \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --task-stdin < /approved/private/task.txt

python -m skeleton.jeeves.agent.native_cli \
  --mode durable-agent --run-id jeeves_job_001 --replay-result \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --task-stdin < /approved/private/task.txt

python -m skeleton.jeeves.agent.native_cli \
  --mode durable-agent --run-id jeeves_job_001 --resume-run \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --task-stdin < /approved/private/task.txt
```

For successful inspection or explicit recovery, repeat the *identical*
task, budget, principal and installed model identity. A changed source text,
even with the same run ID, is rejected. **Do not resume** terminal or
uncertain runs; inspect the journal, authoritative native request state and
outbox separately. No implicit startup recovery or supervisor retry exists.

Durable mode intentionally rejects source tools and all ephemeral tool
grants. The existing non-durable `agent` lane supports signed readonly
source retrieval; cross-process tool-effect reconciliation is not yet
qualified for durable restoration. Real user-visible agent answers still
require the installed local GGUF and independent quality proof.

## Validation and holds

- Source-only CI uses a deterministic **SYNTHETIC** GGUF-shaped generator
  with *real* SQLite/WAL, SessionGate, provider adapter, native receipt replay,
  strict Jeeves planner and checkpoint writes.
- Focused regressions cover owner isolation, input rebinding, SQLite payload
  tampering, missing rows, history retention, changed root hash, pending
  inference, cold reopen and explicit pre-inference planner recovery.
- A synthetic crash *after the native commit, before the planner checkpoint*
  must preserve a durable intent and reject recovery without re-generating.
- A passing test here is **not** a physical GGUF forward pass, interrupted
  native cancellation test, a Windows 11/WSL2 clean install, a pressure
  qualification, model license verification or a release certificate.
- PR #4700 remains draft and stacked on #4699. Exact-head security, release,
  consumer and native validation gates are still mandatory before promotion.

## Run-scoped working-memory continuity

The durable reasoning lane now uses the existing Jeeves MemoryManager with
an append/update custody table, `jeeves_native_memories`, in the same private
SQLite transaction authority. The exact memory ID, namespace, content,
source, trust, salience, evidence refs, expiration and recall counters are
stored and validated before cold recovery. No other run or subject can be
imported into the active planner. A failed durable memory write now stops
the durable reasoning lane; the ordinary best-effort memory error swallowing
is deliberately not used here. Unreviewed privacy deletion and silent cache
eviction are held rather than discarding only the process copy. Durable
retention/deletion lifecycle remains a separate release hold.


## Read-only crash inspector without GGUF

When a model cannot activate, a local operator can inspect the private state
without initializing native inference or mutating SQLite:

```bash
python -m skeleton.jeeves.agent.native_cold_doctor \
  --state-dir /approved/private/state --tenant local --subject operator \
  --model-sha256 ACTUAL_MODEL_DIGEST \
  --tokenizer-sha256 ACTUAL_TOKENIZER_DIGEST \
  --run-id jeeves_job_001
```

The protected read-only SQLite connection checks checkpoint history,
hash links, terminal-result bytes, scoped memory record integrity, native
inference-intent status, principal-specific pending/held native requests and
tool effect counts. The resulting diagnostic has no prompt, response or memory
body. It never resumes, retries, loads model bytes, relaxes a hold or certifies
physical GGUF/device readiness. A missing model, stale approval or uncertain
effect remains a separate explicit release hold.


## Approved real-model multi-turn acceptance

The `native_session_cli` exercises one source-installed GGUF over several
host-bound turns with strict input/output capacity and an optional independent
cold model reload and SQLite replay. Example operator-owned casebook:

```json
{"schema":"jeeves.native_session_casebook.v1","cases":[
  {"case_id":"intro","prompt":"Describe your available local capabilities."},
  {"case_id":"followup","prompt":"Which capabilities require explicit approval?"}
]}
```

```bash
python -m skeleton.jeeves.agent.native_session_cli \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --approve-native --casebook-stdin \
  --cold-replay < /approved/private/cases.json
```

The operator CLI requires an independent source-verified installed model.
It returns digests and measured usage rather than private text. Every fresh
turn requires an authoritative SQLite commit; cold replay must use those
previous request IDs, with zero additional native generation. An absent source
receipt, changed model identity, model failure, uncertain native request,
timeout, incorrect objective hash or changed casebook is a hold. Source-only
CI intentionally substitutes a synthetic generator but exercises the actual
supervisor, DB, transcript and CLI call path. No physical acceptance is
claimed until an approved laptop invocation captures real receipts.


## Deterministic native batch conveyor

`native_batch_cli` runs finite user-authorized tasks against one source-installed
GGUF. Each task receives a **stable identity** derived from the tenant, operator,
actual model/tokenizer and requested batch/task IDs. Repeating an identical
approved casebook checks the original SQLite request and replays its committed
answer **without** a second model call. A changed prompt under the same identity
is rejected by the canonical request digest check. A timed-out or uncertain
native effect is held, not silently retried.

```json
{"schema":"jeeves.native_batch_casebook.v1","batch_id":"demo_batch","tasks":[
  {"task_id":"first","prompt":"Give one bounded answer."},
  {"task_id":"second","prompt":"Provide a local-only follow-up."}
]}
```

```bash
python -m skeleton.jeeves.agent.native_batch_cli \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --approve-native --batch-stdin \
  < /approved/private/batch.json
```

The CLI caps tasks, all prompt bytes, full output-token reservations,
wall time, model identity and per-job latency before starting new work.
It emits only hashes, counts and receipt identities, not private source text.
Its `--maximum-jobs` ceiling reaches 1,000, but this is **bounded serial
work**, not proof of 1,000 simultaneously executing GPUs or hardware workers.
The queue and readiness layers do not replace source-attested GGUF activation,
the existing private SQLite authority or real device qualification.
