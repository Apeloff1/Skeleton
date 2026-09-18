# SMB Shift Manager + Secretary architecture

This document defines the supervisory layer for the existing night-shift and idle-shift bot teams.

## Roles

### SMB Shift Manager
- Owns the shared operational plan across Night Shift and Idle Shift.
- Tracks workers clocked in, active assignments, last heartbeat, overtime minutes, and overtime task context.
- Rebalances work between teams when one shift is overloaded, idle, blocked, or underutilized.
- Calls the configured model API to synthesize research, evaluate backlog state, produce delegation decisions, and regenerate the shared plan every 30 minutes.
- Records all material model calls, plan revisions, delegation events, and staffing decisions.
- Uses bounded retries, request timeouts, idempotency keys, and explicit budgets so a failed model/API dependency cannot silently wedge the supervisor.

### Secretary
- Reads the same shared plan and backlog state.
- Calls the configured model API every 15 minutes to identify missing work, validation tasks, research needs, tests, documentation, cleanup, and follow-up tasks.
- Adds workload only through the plan store; it never bypasses the Shift Manager's staffing or safety rules.
- Deduplicates proposed tasks against open, completed, and recently rejected work before adding them.
- Marks every task with provenance: source, model, timestamp, rationale, dependencies, expected output, and target team.

## Shared model gateway

Both agents use one model gateway interface rather than embedding provider-specific HTTP calls in scheduler logic. The gateway is responsible for:

- model/provider selection from environment configuration;
- authenticated API calls;
- structured JSON responses;
- timeout and retry policy;
- token/cost limits;
- correlation IDs and audit logging;
- optional research-provider adapters;
- graceful fallback when a provider is unavailable.

No credentials are committed to the repository. Runtime credentials are read from environment variables or the existing secret manager.

## Cadence

- Secretary workload enrichment: every 15 minutes.
- SMB Shift Manager full plan refresh: every 30 minutes.
- Worker heartbeat/staffing refresh: frequent lightweight polling, independent from model calls.

The 15-minute Secretary pass is intentionally offset from the 30-minute manager pass where possible, so the manager can consume newly added workload rather than racing the Secretary.

## Plan refresh pipeline

1. Snapshot staffing, heartbeat, overtime, work-in-progress, queue depth, blocked work, recent failures, repository state, and completed work.
2. Gather research from configured sources and internal project state.
3. Ask the model for a structured plan proposal.
4. Validate proposal schema, scope, dependencies, duplicates, budgets, and safety constraints.
5. Merge the proposal into the canonical plan.
6. Assign/delegate only work that passes policy and capacity checks.
7. Emit an immutable audit event for the plan revision.

## Minimum plan item schema

Each plan item should include:

- `id`
- `title`
- `description`
- `priority`
- `target_team`
- `owner` (optional until assigned)
- `status`
- `dependencies`
- `source`
- `rationale`
- `research_refs`
- `expected_output`
- `validation`
- `created_at`
- `updated_at`

## Staffing and overtime

The manager maintains a worker ledger with:

- worker ID and team;
- clock-in and clock-out timestamps;
- current task;
- active/idle/blocked state;
- last heartbeat;
- normal shift minutes;
- overtime minutes;
- overtime task IDs and descriptions;
- cumulative overtime by rolling period.

Overtime is observable and attributable, not merely a boolean. The manager should prefer rebalancing or handing off work when a configured overtime threshold is exceeded.

## Safety and failure behavior

- Model output is advisory until schema/policy validation passes.
- A model failure cannot erase the prior plan.
- A Secretary failure cannot block Shift Manager refreshes, and vice versa.
- Duplicate jobs are rejected before enqueue.
- All external calls have finite timeouts and bounded retries.
- Rate limits and cost ceilings are enforced centrally.
- The canonical plan and worker ledger are persisted so restarts recover state.
- Every mutation is logged with correlation ID and actor (`shift-manager`, `secretary`, or worker).
