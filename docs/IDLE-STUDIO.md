# Idle Studio: 1,000 logical repository workers

Idle Studio is the daytime/idle-capacity counterpart to scheduled night maintenance. It exposes **1,000 stable model-driven worker identities** while deliberately activating only a bounded subset when the repository has spare capacity. The goal is high throughput without 1,000 simultaneous API calls, duplicate edits, branch collisions, or uncontrolled spend.

## Operating model

The fleet is split evenly across 20 specialties: game systems, game AI, simulation, graphics, physics, networking, tools/editor, backend, architecture, reliability, testing, security, performance, data, API contracts, observability, documentation, build/release, UX/accessibility, and research/benchmarking. Each worker has a stable `idle-NNNN` identity and deterministic rendezvous assignment, so the same task maps consistently to an appropriate specialist.

Every 15 minutes the workflow checks Actions activity. If another repository workflow is queued or running, Idle Studio exits without consuming model budget. When the repository is idle it builds a priority queue from failed workflows, open issues, open pull requests that may need regression coverage, and unchecked `BACKLOG.md` items. Existing Idle Studio PR markers prevent duplicate claims.

The default sweep activates up to 8 logical workers and allows up to 4 task attempts / 6 model calls. These are concurrency and cost controls, not fleet-size limits. Repository variables can raise bounded throughput after observing CI/API capacity.

## Model and credentials

The controller uses the existing `ChatGPTReasoner` Responses API adapter. Configure the repository secret:

- `OPENAI_API_KEY` — the API credential. It is read into the controller and removed from the process environment before any generated content could be handled by child processes.

Optional repository variable:

- `OPENAI_MODEL` — model identifier. If unset, the adapter's default is used.

The controller never places the API key or GitHub token in prompts, PR bodies, logs, artifacts, generated files, or Git remotes.

## Mutation boundary

A model can propose complete replacement text only under:

- `skeleton/`
- `backend/`
- `tests/`
- `docs/`

It cannot alter `.github/`, `.git/`, `.env*`, deployment/infra paths, secrets, root policy/config files, or binary assets. Traversal, absolute paths, duplicate paths, oversized files, oversized batches, invalid Python, invalid JSON, and obvious private-key material are rejected before mutation.

Model-authored code is **not executed by the Idle Studio workflow**. Python is compiled syntactically and JSON is parsed, but behavioral execution is deferred to ordinary repository CI/security gates. This keeps model output on the untrusted side of the credential boundary.

Accepted proposals are committed through the GitHub Git-data API to deterministic `idle-studio/<worker>/<task-fingerprint>` branches and opened as normal pull requests. The controller rechecks that `main` still equals the checked-out SHA immediately before each mutation and fails closed if it moved. The studio never merges its own work.

## Backpressure and deduplication

The workflow uses a single concurrency group, stable task fingerprints, PR-body claim markers, and an open-PR ceiling. By default it stops creating new work when 12 Idle Studio PRs are already open. This prevents the 1,000-worker logical fleet from turning into an unreviewable queue.

## Throughput controls

Supported repository variables:

| Variable | Default | Bound | Purpose |
| --- | ---: | ---: | --- |
| `IDLE_STUDIO_ACTIVE_WORKERS` | 8 | 1–32 | specialists available in one sweep |
| `IDLE_STUDIO_TASKS_PER_RUN` | 4 | 1–12 | task attempts in one sweep |
| `IDLE_STUDIO_MAX_MODEL_CALLS` | 6 | 1–16 | hard API-call budget per sweep |
| `IDLE_STUDIO_MAX_OPEN_PRS` | 12 | 1–50 | queue backpressure ceiling |

Additional controller-only limits bound files and bytes per proposal. Raise throughput gradually; API rate limits and CI capacity are the real bottlenecks, not the logical fleet size.

## Capability principle

"1,000 bots" here means 1,000 persistent specialist identities and routing slots, not 1,000 wasteful simultaneous runners. This is closer to how large agent systems are made operational: a scheduler owns leases and budgets, specialists own bounded tasks, generated changes are isolated, and independent verification decides what survives.
