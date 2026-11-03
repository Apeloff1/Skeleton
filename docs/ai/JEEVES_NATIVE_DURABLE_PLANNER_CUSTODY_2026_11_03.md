# Jeeves native durable planner custody (source-only, November 3 2026)

## Scope

This extension to PR #4700 adds **principal-bound agent checkpoint history**
to the canonical protected execution-spine SQLite connection, rather than
opening an unanchored SQLite file or replacing the existing native request,
model receipt, source manifest, WAL or outbox authorities.

The additive \`jeeves_native_runs\`, \`jeeves_native_checkpoints\`, and
\`jeeves_native_inflight\` tables are contained within the same descriptor-
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

The existing cross-process \`SessionGate\` is held across the complete agent
run or explicit resume, rather than only across each GGUF request. Native
SQLite itself still owns per-request serialization and uncertain-effect fences.

## Operator workflow

\`native_cli\` exposes three **operator-initiated** commands (the provided
\`task.txt\` is a private local file, not a repository artifact; source proof
and model installation must already have been independently approved):

\`\`\`bash
python -m skeleton.jeeves.agent.native_cli \
  --mode durable-agent --run-id jeeves_job_001 \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --task-stdin < /approved/private/task.txt

python -m skeleton.jeeves.agent.native_cli \
  --mode durable-agent --run-id jeeves_job_001 --inspect-run \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --task-stdin < /approved/private/task.txt

python -m skeleton.jeeves.agent.native_cli \
  --mode durable-agent --run-id jeeves_job_001 --resume-run \
  --model-root /approved/private/model --state-dir /approved/private/state \
  --tenant local --subject operator --task-stdin < /approved/private/task.txt
\`\`\`

For successful inspection or explicit recovery, repeat the *identical*
task, budget, principal and installed model identity. A changed source text,
even with the same run ID, is rejected. **Do not resume** terminal or
uncertain runs; inspect the journal, authoritative native request state and
outbox separately. No implicit startup recovery or supervisor retry exists.

Durable mode intentionally rejects source tools and all ephemeral tool
grants. The existing non-durable \`agent\` lane supports signed readonly
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
