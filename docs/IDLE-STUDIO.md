# Idle Studio: 1,000 logical repository workers

Idle Studio is the idle-capacity counterpart to scheduled night maintenance. It exposes **1,000 stable model-driven worker identities** while activating only a bounded subset when the repository has spare capacity. The goal is high engineering throughput without 1,000 simultaneous API calls, duplicate edits, branch collisions, uncontrolled spend, or direct writes to `main`.

## Studio pipeline

Each productive run follows a gated studio loop:

1. **Repository intake** snapshots recent Actions runs, open issues, open pull requests, and unchecked `BACKLOG.md` work.
2. **Planner** uses a bounded model call to choose the highest-value independent tasks from deterministic candidates.
3. **Specialist builder** is selected from the 1,000-worker fleet using stable role-aware rendezvous assignment.
4. **Deterministic policy** rejects unsafe paths, traversal, binary/control-plane changes, excessive scope, invalid Python/JSON, and private-key material.
5. **Independent senior reviewer** is selected from testing, security, reliability, architecture, or research/benchmark roles and must explicitly approve the proposal.
6. **Sealed-package validation** re-parses the exact reviewed file contents in a separate step with no model or GitHub credentials.
7. **Publication** runs with a GitHub token but no model credential, rechecks current `main`, open Studio PR capacity, and duplicate task claims, then opens ordinary `idle-studio/*` pull requests.
8. **Repository CI/security gates** remain the execution and merge authority. Idle Studio never merges its own work.

The planner, builder, and reviewer are model-driven. Model output is always treated as untrusted data.

## Fleet

The logical fleet is split evenly across 20 specialties: game systems, game AI, simulation, graphics, physics, networking, tools/editor, backend, architecture, reliability, testing, security, performance, data, API contracts, observability, documentation, build/release, UX/accessibility, and research/benchmarking. Each worker has a stable `idle-NNNN` identity and shard, giving the scheduler 1,000 persistent routing slots without creating 1,000 concurrent processes.

Worker assignment is deterministic for a task, favors roles that match the task kind, and avoids assigning the same worker twice in one sweep. Senior review is independently routed and cannot be performed by the builder that authored the proposal.

## Idle detection and work intake

Every 15 minutes the workflow checks repository Actions activity. If another repository workflow is queued or running, Idle Studio exits before consuming model budget. When the repository is idle it builds a priority queue from:

- failing or timed-out workflows;
- open security/bug issues;
- open pull requests that may need regression coverage;
- unchecked `BACKLOG.md` items.

Existing Idle Studio PR markers prevent duplicate claims. A fresh claim check is repeated again immediately before publication so a retry or overlapping repository event does not create duplicate work.

## Credential separation

The workflow deliberately separates authority across steps:

- **Propose:** receives `OPENAI_API_KEY`, but no GitHub token is exported to the process. It writes a model-reviewed package, redacted JSONL audit, and human report.
- **Validate:** receives neither the model key nor a GitHub token. It verifies the package checksum, worker identities, independent approval, proposal paths, size bounds, and static syntax/JSON contracts.
- **Ledger:** receives a GitHub token only to append the human report and redacted machine audit to the durable `bot: idle studio ledger` issue.
- **Publish:** receives a GitHub token but an explicitly empty `OPENAI_API_KEY`. It can create isolated branches and pull requests only after the sealed package passes validation.

The checked-out controller always comes from trusted `main`; manual workflow dispatch is restricted to `main`. Checkout credentials are not persisted.

## Model and API

The controller uses the repository's bounded `ChatGPTReasoner` Responses API adapter. Configure the repository secret:

- `OPENAI_API_KEY` — API credential used only in the proposal/review step.

Optional repository variable:

- `OPENAI_MODEL` — model identifier. If unset, the adapter default is used.

Repository and GitHub text is redacted before model submission and is explicitly treated as untrusted evidence, never instructions. Model responses are bounded before parsing.

## Mutation boundary

A model can propose complete replacement UTF-8 text only under:

- `skeleton/`
- `backend/`
- `tests/`
- `docs/`

It cannot alter `.github/`, `.git/`, `.env*`, deployment/infra paths, secrets, root policy/config files, or binary assets. Traversal, absolute paths, duplicate paths, oversized files, oversized batches, invalid Python, invalid JSON, and obvious private-key material are rejected before mutation.

Model-authored code is **never executed by the Idle Studio controller**. Python is compiled syntactically and JSON is parsed; behavioral execution belongs to the repository's ordinary PR CI/security gates.

Accepted proposals are committed through the GitHub Git-data API to deterministic `idle-studio/<worker>/<task-fingerprint>-<run>` branches and opened as normal pull requests. Publication fails closed if `main` moved after the trusted snapshot.

## Audit and visibility

Every run attempts to append a durable entry to the open issue titled `bot: idle studio ledger`, including no-op, busy, missing-key, rejected, and productive runs. The ledger comment contains:

- run URL;
- human-readable run report;
- selected planner tasks and rationale when available;
- builder/reviewer identities for accepted work;
- redacted machine audit events.

The workflow summary mirrors the human report. Nothing requires silent autonomous mutation.

## Backpressure and budgets

The workflow uses a single concurrency group, stable task fingerprints, PR-body claim markers, a model-call budget, per-change file/byte limits, and an open-PR ceiling. Defaults are intentionally bounded:

| Variable | Default | Bound | Purpose |
| --- | ---: | ---: | --- |
| `IDLE_STUDIO_ACTIVE_WORKERS` | 8 | 1–32 | specialists available in one sweep |
| `IDLE_STUDIO_TASKS_PER_RUN` | 4 | 1–12 | task attempts in one sweep |
| `IDLE_STUDIO_MAX_MODEL_CALLS` | 6 | 1–16 | planner/builder/reviewer API-call budget |
| `IDLE_STUDIO_MAX_OPEN_PRS` | 12 | 1–50 | queue backpressure ceiling |

With the default six-call budget, the controller can spend one call on planning and up to two builder/reviewer pairs. Larger configured budgets increase bounded throughput, not authority.

## Capability principle

"1,000 bots" means 1,000 persistent specialist identities and routing slots, not 1,000 wasteful simultaneous runners. The scheduler owns budgets and task assignment; builders own bounded proposals; senior reviewers independently challenge them; deterministic code owns policy; CI/security gates decide what survives. This keeps idle capacity useful while preserving a strict trust boundary around credentials and repository mutation.
