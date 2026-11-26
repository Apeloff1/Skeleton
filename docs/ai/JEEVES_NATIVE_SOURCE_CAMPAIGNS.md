# Jeeves offline native source-work campaigns — operational runbook

## What this actually builds

The local-first code-authoring path now has an explicit serial **campaign**
above the existing real installed GGUF worker, canonical SQLite owner,
verified original source context, finite native source self-repair,
private no-clobber GGUF proposal escrow, and source review workbench.

One operator-reviewed campaign can run **1–12 original coding tasks** in a
predetermined, dependency-ordered sequence. Each task uses the same
operator-selected local model/state/principal, with its own independently
reviewed source goal, token/deadline budget, original file snapshot,
native request SHA-256 and new private `*.source.json` output.

This is real production orchestration of the existing native model interface:
it calls `execute_native_request` indirectly through the existing
`execute_escrow_request` path for every task. The native runner creates
an independently committed canonical SQLite session per task; its code is
never printed to normal stdout. It is NOT a second inference backend.

**Dependencies express task ordering, not implicit model memory or
propagation of previous generated files.** The original checkout is
read-only throughout. If the output of a previous job should inform the
next, the operator must inspect it, explicitly select its source under
the existing review/source-context controls and start a fresh campaign.
No hidden cross-task context or unreviewed generated-code execution.

## Phase 1 — independently inspect native tasks

First use the pre-existing headless native CLI for each proposed goal:

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_code_cli < native-inspect.json
```

The native inspector returns an exact `job_sha256` and, when selected
source files exist, an exact `source_context_sha256`. Neither inspection
runs a model or changes project files.

Construct each campaign `native_request` from that reviewed request by
setting `action` to `generate` and `job_sha256` to the inspected full
digest. Copy the same digest into each task's `expected_job_sha256`.
Do not replace the approved original goal or change the model configuration.

Every native request still strictly includes the existing required fields:
`schema`, `action`, `project_root`, `model_root`, `state_dir`,
`tenant`, `subject`, `goal`, `format`, `maximum_attempts`,
`source_paths`, `source_context_sha256`, `job_sha256`,
`context_tokens`, `max_output_tokens`, `threads`,
`gpu_layers`, `inference_ms`, `capacity_budget_bytes`.

## Phase 2 — inspect full finite campaign

Create a JSON request with exactly these fields:

```json
{
  "schema": "jeeves.desktop.native-source-campaign.v1",
  "action": "inspect",
  "project_root": "/absolute/original-project",
  "journal_file": "/absolute/owner-private/work.jeeves-campaign.jsonl",
  "manifest_sha256": null,
  "recheck_original_source": false,
  "tasks": [
    {
      "task_id": "module-one",
      "depends_on": [],
      "target": "/absolute/owner-private/module-one.source.json",
      "expected_job_sha256": "FULL_NATIVE_INSPECTED_JOB_SHA256",
      "native_request": {
        "schema": "jeeves.desktop.headless-native-source-work.v1",
        "action": "generate",
        "project_root": "/absolute/original-project",
        "model_root": "/absolute/approved-model",
        "state_dir": "/absolute/private-sqlite-state",
        "tenant": "operator-tenant",
        "subject": "operator",
        "goal": "Author an original bounded module for the selected project",
        "format": "new-files",
        "maximum_attempts": 1,
        "source_paths": [],
        "source_context_sha256": null,
        "job_sha256": "SAME_FULL_NATIVE_INSPECTED_JOB_SHA256",
        "context_tokens": 4096,
        "max_output_tokens": 1024,
        "threads": 4,
        "gpu_layers": 0,
        "inference_ms": 60000,
        "capacity_budget_bytes": 1000000000
      }
    }
  ]
}
```

The digest placeholders must be replaced with **actual** lowercase SHA-256
values from prior task inspections; this example is a structural template,
not executable input with valid approvals.

Run:

```bash
python -m skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_native_campaign_cli < inspect.json
```

The campaign inspector re-hashes the original source context and each
reviewed native task, verifies unique target names/ownership and
dependencies, total budgets and owner identity, and produces a single
`manifest_sha256` covering the **exact entire campaign**. It starts
no model, opens no SQLite session and writes no file.

A maximum 12 tasks, 24 total source-repair attempts, 65,536 requested
output tokens and 1,200,000 milliseconds of cumulative native inference
can be approved. This is a budget ceiling, not a promised runtime estimate.

## Phase 3 — execute the unchanged approved campaign

Change `action` to `run`, set `manifest_sha256` to the exact digest
from Phase 2, and keep the other fields unchanged. The operator must use
all three distinct flags:

```bash
python scripts/jeeves_native_campaign.py \
  --approve-campaign --approve-native --approve-private-storage < run.json
```

Before starting a model, Jeeves checks all task source snapshots,
the entire campaign source/model principal, the private journal
directory and **every** output target. All targets and the journal
must be nonexistent leaves under the *same existing 0700 owner-private
directory* outside the original project, installed model and SQLite
state directories.

The writer creates a new 0600 private audit file using O_EXCL, pins
the parent directory and **fsyncs the BEGIN and ATTEMPT record before
any corresponding GGUF/SQLite work**. Each original task calls the
existing native source generator and existing separate private escrow.
A saved escrow is independently cold-verified by complete file/job SHA,
source graph and exact current project source before the audit records
SAVED. Only then may a following dependent task run. At the end, the
audit writes COMPLETE and cold-verifies every private source escrow
again. Generated source never executes.

The journal is a **non-authoritative audit**. The existing canonical
SQLite execution ledger remains the only authority for uncertain
committed native requests. A crash or missing SAVED event after ATTEMPT
means **model work may already have committed**. There is no automatic
retry, resume, reconstructed success or silent cleanup of unknown file
inodes. The operator must inspect canonical SQLite and owner-private
files and create a **new approved campaign** for work not completed.

## Phase 4 — cold audit without a model

With `action` set to `verify`, the same exact manifest is required,
but no approval flags. Set `recheck_original_source` true to also
verify that every saved model proposal still matches the *current*
original project source. It never invokes GGUF or causes an SQLite
write. The journal hash chain, task sequencing, intent-before-result,
all saved file bytes, source identities and exact receipt lineage are
independently checked. Stale, missing, duplicated, damaged or modified
file evidence rejects completion.

If `verify` reports an incomplete or uncertain campaign, preserve all
source/release holds. It does not provide a resume authority.

## Limits and guarantees

- POSIX/WSL2 only for descriptor-based private custody. No native
  Windows filesystem assertion.
- No model-provider SDK, network acquisition, shell/Git invocation,
  source execution, hidden tool permission, project write, or retry.
- No new SQLite authority, ledger, checkpoint, inference backend or
  implicit cross-task memory. Each approved task obtains its own
  canonical SQLite session from the existing runtime.
- No source text, private file paths or model prompts appear in stdout.
  The private journal may contain approved absolute escrow paths through
  the user request, but its own records contain only task IDs and hashes.
- No full laptop/GGUF rights/installation/physical-device, GPU, native
  cancellation, file-runtime integration, completion percentage or
  release certification is implied by source-only CI.

## Source validation commands

```bash
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_native_campaign.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_native_code_cli.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_native_proposal*.py' -v
python -m unittest discover -s skeleton/testing -p 'test_jeeves_desktop_*.py' -v
python -m compileall -q skeleton/ai/runtime/operational_ai/laptop_runtime
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Preserve all draft, dependency, security, device and final-head release holds.
