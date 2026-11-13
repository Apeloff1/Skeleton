# Jeeves serial durable work batches — one installed GGUF, one SQLite owner

Jeeves now has a human-controlled **multi-task work batch** on top of its
original source-bound local model and canonical `NativeDurableJeevesAgent`.

The feature is designed for the operator who wants substantial successive
tasks carried out by a local AI without launching parallel model processes,
unbounded virtual workers or a second persistent queue database. It
**executes sequentially in the running desktop**, not in the background after
you close the app.

## Operator use

1. Connect an actually installed, licensed, source-checked GGUF in the
   private desktop. The original private SQLite principal/model binding and
   capacity/pressure supervisors still apply.
2. Choose **Run serial work batch**. In the dedicated review window,
   enter a strict JSON list of up to 32 approved tasks. For example:

```json
{
  "schema": "jeeves.desktop.durable-work-batch.v1",
  "items": [
    {
      "title": "Original offline engine module",
      "task": "Implement the new original native engine module and explain the result.",
      "maximum_steps": 8,
      "maximum_model_calls": 8,
      "maximum_wall_seconds": 180
    },
    {
      "title": "Document source integration",
      "task": "Describe concrete integration requirements for that module.",
      "maximum_steps": 8,
      "maximum_model_calls": 8,
      "maximum_wall_seconds": 180
    }
  ]
}
```

3. Click **Review entire source work batch**. The pure finite parser
   validates every task, enforces total budgets, assigns a unique
   `wrun_...` durable SQLite work ID **before any model execution**, and
   computes one canonical manifest SHA-256 covering the exact UTF-8
   task text, run IDs and resources.
4. Read all task titles and run IDs, then **enter the full manifest
   SHA-256**. The batch cannot run before you explicitly approve its
   unchanged source bytes. Changing the JSON invalidates approval.
5. Click **Execute approved tasks SERIALLY**. The UI starts one
   application-owned worker thread. It calls the **already connected**
   native child using the existing private bounded IPC and
   `durable action=start` once per task, in order. Every task is
   recorded in the canonical SQLite durable journal under its
   **original** visible run ID. No new queue database is created.
6. Watch each committed/held status in the review list. A successful
   response must have a true canonical SQLite `terminal-committed`
   receipt, matching run ID, source/model digest and zero tool calls.
   The runner never interprets an unverified model string as success.
7. Use **Stop AFTER current task** to stop the sequence between native
   calls. This does not interrupt a currently committing SQLite/model
   effect. Disconnection, pressure revocation, a failed native step,
   malformed result or unknown effect stops the batch; **no automatic
   retry** or next-task execution occurs.

On a cold restart, the operator can use the already implemented
**Inspect / Resume explicitly / Replay terminal** controls with the
original run ID, exact task and budgets. The batch does not resume
automatically and does not silently retry an uncertain native effect.

## Bounds

| Control | Maximum |
|---|---:|
| Tasks per reviewed batch | 32 |
| JSON input | 256 KiB |
| Original task UTF-8 bytes | 32 KiB each |
| All original prompt bytes | 128 KiB |
| Model calls per task | 64 |
| Aggregate native model calls | 512 |
| Wall-clock seconds per task | 600 |
| Aggregate requested wall budget | 7,200 seconds |
| Concurrent native model workers | 1 |
| Independent model providers | 1 |
| Implicit source/tool grants | 0 |
| Automatic retries or resumes | 0 |

Each request is still constrained by the installed model token ceiling,
exact native source/rights admission, strict step/tool budget, SQLite
journal, private IPC watchdog and any enabled live memory/cgroup/disk
pressure supervisor.

The batch runner does not perform source-writing actions on behalf of
a model. If Jeeves outputs new files or edits, use the separately
implemented **reviewed new-file** or **existing-file candidate**
operator interfaces and their individual hash approvals.

## Limits of completion evidence

A model task may produce a plausible answer without actually creating
a source file. The durable work receipt proves the model committed
that answer and its source/tenant/request identity; it does **not**
certify that a complete software ecosystem or test suite is finished.
Application completion percentages require independent, measurable
feature acceptance criteria and actual laptop qualification.

The source-only test suite exercises immutable review, 20-task batches,
single-worker sequential execution, per-task IDs, failed native holds,
manual stop, canonical receipt verification, no shell/network operations
and no implicit retries. This is **not** proof of actual licensed-GGUF
inference, Windows 11/WSL2 operation, hardware pressure or release.


## Whole-batch exclusive native lease

The private desktop bridge now locks the **entire** reviewed work sequence,
not merely each individual SQLite IPC request. A second thread's chat,
agent, history, source status or durable request is denied before writing
a frame while the batch owner holds this lease. A second batch also cannot
start concurrently. The same operator-owned runner thread alone may submit
the approved individual work orders. A pressure watchdog can still revoke
the native child; its abort path does not wait on the batch lock.

This closes an important race where an ordinary GUI request could previously
run between two individually valid durable tasks and alter model/SQLite
state before the following task. The lease is in-process and held only by
the already authenticated desktop bridge; it is **not** a distributed
scheduler, cross-device lock or hardware qualification.

## Cold-restart batch recovery

The serial work-batch GUI can explicitly export the **complete original**
task budget/ID manifest to a *new* descriptor-anchored owner-private `0600`
file under a pre-existing private `0700` POSIX/WSL2 directory. Imported
recovery batches cannot be started or resumed; only a selected original
work order's sealed SQLite checkpoint may be inspected or replayed after
the operator supplies the exact original manifest digest. Nothing is
silently reissued. Sensitive task text is present in the private export;
never put it into Git. See
`docs/ai/JEEVES_PRIVATE_BATCH_COLD_RECOVERY.md`.
