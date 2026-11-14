# Jeeves Advanced Native Campaign — first-laptop operator experience

The existing Tk Jeeves desktop now exposes an **Advanced native coding
campaign** button inside the code/source composer. It uses the same real
installed GGUF backend, canonical SQLite execution owner, original source
readers, verified source escrow and combined source delivery—not a new
model runtime, background autonomous agent or hosted provider.

## Desktop operation

1. Disconnect any active Jeeves native conversation before starting a
   coding campaign. One verified local model owner must be active at a time.
   The campaign workbench is a separate single-instance operator window.
2. Paste strict full campaign JSON with the `inspect` action. Every task
   must have its own real native source `job_sha256`, original source
   selection digest, resource ceilings, private target and dependency order.
3. Press **Inspect ORIGINAL campaign**. This is read-only, checking source
   task digests and approval scope without starting a model. Copy the
   resulting full `manifest_sha256` and type it into the approval field.
4. Independently check all three approvals for the exact campaign, actual
   installed local GGUF/SQLite native effects, and no-clobber owner-private
   source file publication. Press **RUN one approved native campaign** and
   confirm the separate desktop dialog.
5. The existing native source-work engine processes tasks in sequence with
   the persistent SQLite identity boundary. The new campaign audit fsyncs
   ATTEMPT *before* each native call; a result counts as SAVED only after
   private source escrow and cold original-source verification.
6. A failed or uncertain native request cannot be retried by clicking the
   same run button. The RAM-only controller consumes native launch authority
   before it calls the backend. If Tk closes or an error occurs, inspect
   source escrow, audit and canonical SQLite before planning new work.
7. Press **Cold verify**. If every source proposal was saved, use **Inspect
   ONE cross-task reviewed source patch** to independently reconstruct the
   complete aggregate Python source/patch/dependency identity. No model
   executes in either inspection.
8. Type the three complete distinct hashes for the **assembly**, **combined
   original manifest**, and **Git patch**. Supply a NEW private destination.
   Approve *one* output: private overlay stage or inert Git patch. The
   existing sealed staging/patch publishers re-check original source again
   and cold-verify the output. No generated code executes automatically.

The same strict JSON-stdin CLI workflow is available without a desktop
display. For large campaigns, review the original task selection and
current project source in a private editor, not public logs or terminal
history.

## Fail-closed UI behavior

- No model starts when a campaign is inspected.
- A changed task JSON or stale native digest is held before reusing prior
  operator approval, even if formatting or task ordering changes.
- A single window owns the campaign approval state in the desktop.
  Duplicate launch clicks raise the same window rather than creating a
  second model authorization. While the campaign window is open, the
  parent desktop cannot open a second GGUF chat worker.
- The local campaign window refuses a native run while the parent chat
  worker or connecting worker is active, or while another parent request
  is busy. The native SQLite side remains the authoritative concurrency
  guard for other processes.
- Private goals, prompt/source bodies, paths, model stderr, tracebacks and
  generated source never enter public UI status receipts. Model errors
  emit generic held notices with explicit uncertainty, never silent retry.
- The window does not close while an operation is running. The parent
  desktop also refuses to exit while its campaign worker is active.
- A failed private-source delivery may already have published bytes;
  the controller consumes that delivery approval so a second attempt
  cannot overwrite or impersonate the first.
- Native run and source publish remain **two separate, explicitly approved
  phases**. The original checkout is never silently patched.

## Validation / scope

After completing the code and UI changes, run:

```bash
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_campaign_operator.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_native_campaign.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_campaign_delivery.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_*.py' -v
python -m compileall -q skeleton/ai/runtime/operational_ai/laptop_runtime
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Passing these source-only tests is NOT evidence of a live physical
Windows 11/WSL2 installation, licensed installed GGUF inference, device
pressure/cancellation, keyboard/visual accessibility, sandboxed generated
code execution, complete app release or an audited +10% completion delta.
Preserve exact-head admission, dependency, privacy and security holds.
