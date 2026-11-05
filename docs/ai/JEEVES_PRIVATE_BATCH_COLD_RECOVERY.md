# Jeeves serial durable batches: private cold-restart recovery

The Jeeves desktop can now explicitly save its reviewed finite serial work
manifest to an **owner-private local file** before running the batch. This
supplies an important missing operational property: after a machine restart,
the operator can recover the **same original prompts, budgets and run IDs**,
inspect the authoritative SQLite checkpoint or replay an already committed
terminal result, without accidentally issuing the original native work again.

## The two separate authorities

**A live submitted run remains in the principal-bound SQLite
`NativeDurableJeevesAgent` journal.** A recovery file is an optional
operator-controlled copy of original task inputs and identifiers, not a new
inference DB, checkpoint, proof of a successful model call, model-license
authorization, installation receipt or source-tool grant.

Every item has an opaque `wrun_<escape><32 hexadecimal characters></escape>`
identifier. The existing batch planner allocates these independently before
execution. Both the complete ordered task/budget list and every immutable
run ID contribute to the 64-character reviewed manifest SHA-256. A changed
prompt or task order is a different batch, never silently reissued.

## Export: deliberately private and no overwrites

1. Connect the independently installed/licensed local GGUF, open **Run
   serial work batch**, paste the original finite task JSON, and select
   **Review entire source work batch**.
2. Record the displayed complete manifest SHA-256 and the per-task original
   run IDs. **Before executing**, enter that full SHA-256 in the
   confirmation field.
3. Select **Save PRIVATE recovery plan**. Choose a **new** path inside a
   pre-existing owner-private directory with POSIX/WSL2 mode `0700`.
   Confirm that the export contains the **complete private original
   prompts** and run IDs. The file is created with `0600`,
   `O_NOFOLLOW`, `O_EXCL` and descriptor-anchored directory custody.
   Existing files are *never* overwritten.
4. Write admission is bounded to 256 KiB, performs full write and
   `fsync` of file/directory, checks inode/ownership/link-count and
   refuses path replacement, symlinks, hardlinks or relaxed permissions.
5. Only then select **Execute approved tasks SERIALLY**. The existing
   single native child retains exclusive ownership of the full sequence,
   and any failed/uncertain task stops subsequent work without retry.

The export is optional. If you choose not to save, manual recovery must use
the exact run ID and original task/budgets from a source you retained
independently.

## Recovery: restored work is permanently read-only

After a full app/device restart and an independently checked new GGUF child
is connected:

1. Open the batch window and select **Restore for READ-ONLY recovery**.
   Supply the private file and the **full original manifest SHA-256**.
2. A descriptor-rooted read checks the actual inode, mode, owner, size,
   original byte count and source path identity both before/after the read.
   Strict canonical UTF-8 JSON, exact key sets, finite budgets, unique
   original run IDs and the complete original batch digest are verified.
3. Restored plans set a local **read-only** status. The button to **start**
   the imported batch is disabled even if the SQLite run has an uncertain
   result. Editing the plan invalidates the review and forces **fresh**
   allocated IDs rather than a silent replay of old ones.
4. Select exactly one original run ID, enter the exact batch SHA-256,
   and choose **Inspect SELECTED original SQLite work** or **Replay
   SELECTED sealed terminal result**. Each requires explicit confirmation.
5. The host calls ONLY the existing `durable` IPC action `inspect` or
   `replay` with that exact original task, run ID and budget under the
   exclusive single-owner bridge gate. **Start/resume is unavailable
   through recovery.** The native bridge/SQLite journal verifies
   principal, model/tokenizer/source epochs and authoritative history.
6. The displayed receipt includes only original run ID, model SHA-256,
   terminal-result hash/status and confirmation that no new native
   generation was performed. It does not print private task text or
   source files. A failed inspection is a hold, not an instruction to retry.

## Security and limitations

The exported file is **sensitive by design**: it stores private original
task contents. Never store it in a shared directory, browser upload,
repository, public issue, synced cloud folder or Git commit. The file
is not encrypted; operating-system private filesystem ownership is the
protection. An attacker with access as the same local OS account can
access it; protect that account accordingly.

This implementation specifically requires Linux/WSL2 POSIX
`O_NOFOLLOW` and owner-private directories. Native Windows filesystem
custody is not certified. It creates no independent licensing attestation,
external model source, network capability, automatic scheduled service,
hidden background workers or authorization to publish generated code.

All source tests use test-only fake workers. Actual local installed GGUF,
Windows 11/WSL2 device pressure/cancellation, cold recovery against
a persisted live SQLite checkpoint and final release gates must still
be physically qualified. A test-only passing source suite cannot certify
hardware or real-model operation.

**Why this is safer than re-starting a held batch:** if the local worker
was interrupted after native generation but before the UI received its
committed receipt, the original SQLite run can be pending, committed or
terminal-held. Retrying its original work order might produce duplicate
effects. A read-only inspection/replay asks the existing durable journal
what it already knows without starting another inference.
